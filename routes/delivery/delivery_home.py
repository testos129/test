from nicegui import ui, app
from fastapi import Request
from fastapi.responses import RedirectResponse
from datetime import datetime, timedelta
import asyncio

from components.theme import apply_background
from components.navbar_delivery import navbar_delivery
from components.footer import footer_bar
from services.auth import get_current_user
from services.users import get_user_info, get_all_pending_order, get_orders_for_delivery_person, update_user_coordinates
from services.distance import haversine_dist
from services.geolocation import start_geolocation_tracking
from services.logging_setup import get_logger
from translations.translations import t


@ui.page("/delivery/home")
async def delivery_home_page(request: Request):

    """Page d'accueil pour les livreurs — affichage des commandes à prendre."""

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies

    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for delivery page home: no valid token, ip: {host}")
        return RedirectResponse('/')

    user_info = get_user_info(user_id)
    if not user_info.get('is_admin', False):
        if not user_info.get('is_confirmed', False) or not user_info.get('is_delivery_person', False):
            logger_user = get_logger('nav')
            logger_user.info(f"Tried to open delivery home page but was denied", extra={"user_id": user_id})
            return RedirectResponse('/')

    # Styles globaux + navbar + cookies
    apply_background()
    navbar_delivery(request)
    footer_bar(request)
    
    lang_cookie = request.cookies.get("language", "fr")

    logger = get_logger('delivery')

    # Lance la récupération en continue de la géolocalisation
    start_geolocation_tracking(user_id)

    # === Contenu de la page ===

    # === Barre de titre ===
    with ui.column().classes("w-full items-center text-center py-8 px-4 fade-in hero"):
        ui.label(t("delivery_space", lang_cookie)).classes("text-3xl font-bold text-gray-900 mb-2")
        ui.label(t("available_orders", lang_cookie)).classes("text-gray-600")

        with ui.row().classes("justify-center gap-4 mb-6"):
            ui.button(t("refresh", lang_cookie), on_click=lambda: refresh_orders.refresh()).props("flat").classes("btn-refresh")
            with ui.button(
                t("my_deliveries", lang_cookie),
                on_click=lambda: ui.navigate.to(f"/delivery/my?lat={user_position['lat']}&lng={user_position['lng']}")
            ).props("flat").classes("btn-my-deliveries"):
                num_orders = len(get_orders_for_delivery_person(user_id))
                if num_orders > 0:
                        ui.label(str(num_orders)).classes("order-badge")


    # === État global ===
    user_position = {"lat": None, "lng": None}
    loading_spinner = ui.spinner(size="lg", color="primary").props("thickness=4").classes("mt-6 hidden")


    # === Pagination ===
    class PaginationState:
        def __init__(self):
            self.current_page = 0
            self.items_per_page = 6

    state = PaginationState()


    # === Conteneurs dynamiques ===
    no_available_container = ui.row()
    orders_container = ui.grid().classes(
        'w-full gap-5 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 items-start justify-center px-6 max-w-6xl mx-auto'
    )
    pagination_container = ui.row().classes('justify-center gap-4 mt-6 w-full')


    # === Fonction : charger commandes de manière asynchrone ===
    async def load_orders():

        """Charge les commandes sans bloquer la boucle principale."""

        return await asyncio.to_thread(get_all_pending_order)


    # === Fonction : géolocalisation asynchrone ===
    async def use_current_location():

        """Demande la géolocalisation sans bloquer le rendu."""

        js_code = """
        new Promise((resolve, reject) => {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    pos => resolve({lat: pos.coords.latitude, lng: pos.coords.longitude}),
                    err => reject("Erreur: " + err.message)
                );
            } else {
                reject("La géolocalisation n'est pas supportée.");
            }
        });
        """
        try:
            coords = await ui.run_javascript(js_code, timeout=10.0)
            if coords:
                user_position.update(coords)
                refresh_orders.refresh()  # ✅ Met à jour les distances une fois la position connue
            else:
                ui.notify("Aucune position reçue", color="red")
        except Exception as e:
            ui.notify(f"Erreur géolocalisation : {e}", color="red")
            logger.warning(f"Error geolocation: {e}", extra={"delivery_user_id": user_id})


    # Récupérer ou lancer la géoloc sans bloquer le rendu initial
    if user_info['current_coords_date']:
        last = datetime.strptime(user_info["current_coords_date"], "%Y-%m-%d %H:%M:%S")
        delta = datetime.now() - last

        if delta < timedelta(minutes=1):
            user_position.update({"lat": user_info['current_lat'], "lng": user_info['current_lng']})
        else:
            ui.timer(0.5, use_current_location, once=True)
    else:
        ui.timer(0.5, use_current_location, once=True)

    # === Logique de pagination ===
    def change_page(delta: int):

        state.current_page = max(0, state.current_page + delta)
        refresh_orders.refresh()


    # === Réservation commande ===
    def reserve_order(order_id: int):

        ui.navigate.to(f"/delivery/order/{order_id}?lat={user_position['lat']}&lng={user_position['lng']}")


    # === Rafraîchissement des commandes ===
    @ui.refreshable
    async def refresh_orders():

        """Rafraîchit l'affichage des commandes disponibles."""

        loading_spinner.classes(remove="hidden")
        no_available_container.clear()
        orders_container.clear()
        pagination_container.clear()

        available_orders = await load_orders()

        if not available_orders:
            loading_spinner.classes(add="hidden")
            with no_available_container:
                ui.label(t("no_orders", lang_cookie)).classes("text-gray-500 text-center mt-8")
            return

        total_pages = max(1, (len(available_orders) + state.items_per_page - 1) // state.items_per_page)
        start = state.current_page * state.items_per_page
        end = start + state.items_per_page
        paginated_orders = available_orders[start:end]

        user_lat, user_lng = user_position["lat"], user_position["lng"]
        if user_lat and user_lng:
            for order in paginated_orders:
                order["distance"] = haversine_dist(user_lat, user_lng, order["lat"], order["lng"])

        with orders_container:
            for order in paginated_orders:

                with ui.card().classes("product-card card-fixed hover-lift transition-all duration-300 hover:shadow-lg"):
                    ui.label(f"{t('commande_num', lang_cookie)}{order['id']}").classes("text-lg font-semibold mb-2 text-gray-800")
                    ui.label(f"{t('client_name', lang_cookie)}{order['customer']}").classes("text-gray-600")
                    # ui.label(
                    #     t("products_list_2", lang_cookie) + ", ".join([f"{name} (x{qty})" for name, qty in order["items"].items()])
                    # ).classes("text-gray-600 text-sm mt-1")
                    ui.label(f"{t('order_total', lang_cookie)}{(order['total'] - order['delivery_cost']):.2f} €").classes("text-gray-700 font-semibold mt-1")
                    ui.label(f"{t('fees', lang_cookie)}{order['delivery_cost']//2:.2f}€").classes("text-gray-700 font-semibold mt-1")
                    ui.label(f"{t('location', lang_cookie)}{order.get('address', 'N/A')}").classes("text-gray-600 text-sm mt-1")


                    if order.get("distance") is not None:
                        ui.label(f"{t('distance', lang_cookie)}{order['distance']:.1f} km").classes("text-gray-600 text-sm mt-1")

                    order_date = order.get("date")
                    if order_date:
                        try:
                            order_date = datetime.strptime(order_date, "%Y-%m-%d %H:%M:%S")
                            now = datetime.now()
                            diff_minutes = (now - order_date).total_seconds() / 60
                            if diff_minutes >= 60:
                                diff_hours = diff_minutes / 60
                                ui.label(
                                    f"{t('time', lang_cookie)}{diff_hours:.0f}{t('hours', lang_cookie) if diff_hours > 1 else t('hour', lang_cookie)}"
                                ).classes("text-gray-600 text-sm mt-1")
                            else:
                                ui.label(
                                    f"{t('time', lang_cookie)}{diff_minutes:.0f}{t('mins', lang_cookie) if diff_minutes > 1 else t('min', lang_cookie)}"
                                ).classes("text-gray-600 text-sm mt-1")
                        except Exception:
                            pass

                    ui.button(t("reserve_order", lang_cookie), on_click=lambda e, oid=order['id']: reserve_order(oid)) \
                        .on('click', lambda e, oid=order["id"]: reserve_order(oid)) \
                        .classes("btn-claim-order")

        # === Pagination ===
        with pagination_container:
            if state.current_page > 0:
                ui.button(on_click=lambda: change_page(-1), icon='chevron_left').props('flat').classes('rounded-full')
            ui.label(f"{t('page', lang_cookie)}{state.current_page + 1} / {total_pages}").classes('text-gray-600 mt-2')
            if state.current_page < total_pages - 1:
                ui.button(on_click=lambda: change_page(1), icon='chevron_right').props('flat').classes('rounded-full')

        loading_spinner.classes(add="hidden")

    # === Affichage initial ===
    await refresh_orders()