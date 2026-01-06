from nicegui import ui, app
from fastapi.responses import RedirectResponse
from fastapi import Request
from datetime import datetime

from services.auth import get_current_user
from components.navbar import navbar
from components.footer import footer_bar
from components.theme import apply_background
from services.users import get_user_info, get_orders_grouped_by_status
from services.items import get_pharmacy
from services.logging_setup import get_logger
from translations.translations import t


@ui.page('/admin/orders')
def admin_orders(request: Request):

    """Page de suivi de toutes les commandes."""

    # === Setup initial ===

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for admin page orders: no valid token, ip: {host}")
        return RedirectResponse('/')
    
    # Vérification des droits admin
    user_info = get_user_info(user_id)
    if not user_info.get('is_admin', False):
        logger_user = get_logger('nav')
        logger_user.info(f"Tried to orders management page but was denied", extra={"user_id": user_id})
        return RedirectResponse('/home')
    
    apply_background()
    navbar(request)
    footer_bar(request)

    logger = get_logger('admin')
    logger.info("Orders page consulted", extra={"admin_user_id": user_id})

    lang_cookie = request.cookies.get("language", "fr")

    # Bouton retour
    with ui.row().classes('w-full p-4 sticky top-0 left-0 z-50 bg-transparent justify-start'):
        ui.button('⬅', on_click=lambda: ui.run_javascript('window.history.back()')) \
            .props('unelevated') \
            .classes('btn-back shadow-lg')


    # === Layout principal ===
    with ui.column().classes("relative w-full items-center text-center py-8 px-4"):

        ui.label(t("order_management", lang_cookie)).classes(
            "text-3xl font-bold text-center my-6")
        

        # === Barre de recherche ===
        # Container relatif pour le champ et les suggestions
        with ui.row().classes("w-full justify-center max-w-xl"):
            
            # Champ de recherche
            search = ui.input(
                placeholder=t("search_orders", lang_cookie)
            ).props("outlined dense clearable id=search-input autocomplete=off").classes("w-full search-input white-input")

            # Bouton search
            with search.add_slot("append"):
                search_button = ui.button(
                    icon="search",
                    on_click=lambda: (reset_page())
                ).props("unelevated id=search-btn")

    # Recherche avec Enter
    ui.run_javascript("""
        document.addEventListener('keydown', function(event) {
            const searchInput = document.getElementById('search-input');
            const searchBtn = document.getElementById('search-btn');
            if (event.key === 'Enter' && document.activeElement === searchInput) {
                event.preventDefault();
                if (searchBtn) searchBtn.click();
            }
        });
        """)
        
    
    # Pagination
    class PaginationState:
        def __init__(self):
            self.current_pending_page = 0
            self.current_progress_page = 0
            self.current_completed_page = 0
            self.items_per_page = 5

    state = PaginationState()

    def change_page(delta: int, title, orders_list, mode):

        """Change la page courante et rafraîchit l'affichage."""

        if mode == 0: 
            state.current_pending_page += delta
        elif mode == 1:
            state.current_progress_page += delta
        else:
            state.current_completed_page += delta

        render_order_column(title, orders_list, lang_cookie, mode=mode)


    def reset_page():

        """Remet la page courante à 0 et rafraîchit l'affichage."""

        state.current_pending_page = 0
        state.current_progress_page = 0
        state.current_completed_page = 0

        render_order_column(t("pending_orders", lang_cookie), all_orders['pending'], lang_cookie, mode=0)
        render_order_column(t("in_progress_orders", lang_cookie), all_orders['in_progress'], lang_cookie, mode=1)
        render_order_column(t("completed_orders", lang_cookie), all_orders['completed'], lang_cookie, mode=2)
        

    @ui.refreshable
    def render_order_column(title, orders_list, lang_cookie, mode):

        """Affiche une colonne de commandes triées avec pagination et expandables.
        
        mode: 
            0 -> pending
            1 -> in_progress
            2 -> completed
        """

        if mode == 0: 
            current_container = pending_container
            current_page = state.current_pending_page
        elif mode == 1:
            current_container = in_progress_container
            current_page = state.current_progress_page
        else:
            current_container = completed_container
            current_page = state.current_completed_page

        current_container.clear()

        query = (search.value or "")
        if query:
            filtered_orders_list = [order for order in orders_list if (query == str(order['order_id']) or query == order['customer'] or query == order['delivery_person'])]
        else:
            filtered_orders_list = orders_list

        total_pages = max(1, (len(filtered_orders_list) + state.items_per_page - 1) // state.items_per_page)
        start = current_page * state.items_per_page
        end = start + state.items_per_page
        paginated_orders = filtered_orders_list[start:end]
        
        # Colonne principale
        with current_container:
            ui.label(title).classes("text-xl font-bold mb-4 text-center")

            if paginated_orders:
                with ui.column().classes('w-full lg:col-span-4 gap-4'):
                    for order in paginated_orders:
                        order_id = order['order_id']
                        with ui.card().classes("w-full product-card card-fixed hover-lift transition-all duration-300 hover:shadow-lg"):

                            ui.label(f"{t('commande_num', lang_cookie)}{order_id}").classes("font-bold")
                            ui.label(f"{t('client_name', lang_cookie)}{order['customer']}")
                            ui.label(f"{t('delivery_person_3', lang_cookie)}{order['delivery_person']}")

                            def format_timedelta(delta):

                                """Affiche le temps depuis une commande"""

                                seconds = int(delta.total_seconds())
                                minutes = seconds // 60
                                hours = minutes // 60
                                days = hours // 24

                                if seconds < 60:
                                    return t("from_few_seconds", lang_cookie)
                                elif minutes < 60:
                                    return f"{t('from', lang_cookie)}{minutes}{t('min_2', lang_cookie)}{t('from_2', lang_cookie)}"
                                elif hours < 24:
                                    return f"{t('from', lang_cookie)}{hours}{t('hour_2', lang_cookie)}{t('from_2', lang_cookie)}"
                                else:
                                    return f"{t('from', lang_cookie)}{days}{t('day', lang_cookie)}{t('from_2', lang_cookie)}"
                                
                            try:
                                order_date = datetime.strptime(order["date"], "%Y-%m-%d %H:%M:%S")
                                delta = datetime.now() - order_date
                                ui.label(f"{format_timedelta(delta)}").classes("mt-2")

                            except Exception:
                                pass

                            # For order completed, display the completion time    
                            if mode == 2:
                                
                                def format_time_taken(start, end):

                                    """Affiche le temps pris par une commande"""

                                    duration_sec = int((end - start).total_seconds())
                                    duration_min = duration_sec // 60
                                    duration_hour = duration_min // 60
                                    duration_day = duration_hour // 24

                                    duration_text = ""
                                    if duration_day > 0:
                                        duration_text += f"{duration_day}{t('day', lang_cookie)} "
                                        duration_hour = duration_hour - duration_day*24
                                        duration_min = duration_min - duration_day*60*24
                                    if duration_hour > 0:
                                        duration_text += f"{duration_hour}{t('hour_2', lang_cookie)} "
                                        duration_min = duration_min - duration_hour*60
                                    if duration_min > 0:
                                        duration_text += f"{duration_min}{t('min_2', lang_cookie)} "
                                    
                                    # Moins d'une minute, on affiche que les secondes, sinon on n'affiche pas les secondes
                                    if duration_sec < 60:
                                        duration_text += f"{duration_sec}{t('sec', lang_cookie)}"

                                    return duration_text
                                
                                try:
                                    start = datetime.strptime(order["date"], "%Y-%m-%d %H:%M:%S")
                                    end = datetime.strptime(order["close_date"], "%Y-%m-%d %H:%M:%S")
                                    duration_text = format_time_taken(start, end)
                                    ui.label(f"{t('completion_time', lang_cookie)}{duration_text}")

                                except Exception:
                                    pass
                            
                            with ui.expansion(t("details", lang_cookie)).classes("w-full"):

                                total_cost_product = order['total'] - order['delivery_cost']
                                ui.label(f"{t('total_cost_product', lang_cookie)}{total_cost_product:.2f}€").classes("font-bold mt-2")
                                ui.label(f"{t('fees', lang_cookie)}{order['delivery_cost']//2:.2f}€").classes("font-bold mt-2")

                                ui.label(f"{t('delivery_address', lang_cookie)}{order['address']}")
                                if order.get('address_details'):
                                    ui.label(f"{t('additional_details', lang_cookie)}{order['address_details']}")
                            
                                # Regrouper les produits par pharmacie
                                pharmacies = {}
                                for item in order["items"]:
                                    pid = item["pharmacy_id"]
                                    if pid not in pharmacies:
                                        pharmacies[pid] = []
                                    pharmacies[pid].append(item)

                                # Afficher chaque pharmacie et ses produits
                                for pharmacy_id, items in pharmacies.items():
                                    pharmacy_info = get_pharmacy(pharmacy_id)
                                    total_pharma = sum(i["qty"] * i["price"] for i in items)

                                    if pharmacy_info:

                                        with ui.expansion(f"🏥 {pharmacy_info['name']}\n{t('address_2', lang_cookie)} {pharmacy_info['address']}", value=True)  \
                                            .classes("ml-2 w-full whitespace-pre-line"):
                                            for item in items:
                                                with ui.row().classes("justify-between text-sm text-gray-700 px-2"):
                                                    ui.label(f"{item['name']} (x{item['qty']})")
                                                    ui.label(f"{item['price'] * item['qty']:.2f}€")
                                            ui.label(f"{t('total_2', lang_cookie)}{total_pharma:.2f}€").classes("text-sm text-gray-700")


                # Pagination
                with ui.row().classes("items-center justify-center gap-2 mt-2"):
                    if current_page > 0:
                        ui.button(on_click=lambda: change_page(-1, title, orders_list, mode), icon='chevron_left').props('flat').classes('rounded-full')
                    ui.label(f"{t('page', lang_cookie)}{current_page + 1} / {total_pages}").classes('text-gray-600 mt-2')
                    if current_page < total_pages - 1:
                        ui.button(on_click=lambda: change_page(1, title, orders_list, mode), icon='chevron_right').props('flat').classes('rounded-full')


    all_orders = get_orders_grouped_by_status()

    # --- 3 colonnes responsive ---
    with ui.grid().classes('w-full gap-5 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 items-start justify-center px-6 max-w-6xl mx-auto'):

        pending_container = ui.column().classes("items-center")
        in_progress_container = ui.column().classes("items-center")
        completed_container = ui.column().classes("items-center")

        reset_page()


    def clear_filter(e):

        value = e.value or ""
        if value.strip() == "":
            reset_page()


    search.on_value_change(clear_filter)