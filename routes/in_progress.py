from nicegui import ui, app
from fastapi.responses import RedirectResponse
from fastapi import Request
import json

from components.navbar import navbar
from components.footer import footer_bar
from components.theme import apply_background
from services.auth import get_current_user
from services.users import record_visit, get_user_info, get_orders_for_customer, get_order_details
from services.items import get_pharmacy
from services.distance import optimize_route
from services.logging_setup import get_logger
from translations.translations import t

            
@ui.page('/orders_in_progress')
def orders_in_progress(request: Request):

    """Page de validation de la commande avec calcul du coût de livraison et itinéraire optimisé"""

    # === Setup initial ===
    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for page in progress: no valid token, ip: {host}")
        return RedirectResponse('/')

    logger = get_logger('nav')

    user_info = get_user_info(user_id)
    if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):  # utilisateur non confirmé et non admin
        logger.info("Access denied for page in progress: not confirmed", extra={"user_id": user_id})
        return RedirectResponse('/')

    record_visit(user_id, '/order')  # Page incluse dans l'historique de navigation

    apply_background()
    navbar(request)
    footer_bar(request)

    lang_cookie = request.cookies.get("language", "fr")

    # === Contenu de la page ===

    # Retour à l'accueil
    with ui.row().classes("w-full justify-between items-center"):
        ui.button(t("return_home", lang_cookie), on_click=lambda: ui.navigate.to("/home")).classes("btn-back")

    pending_orders = get_orders_for_customer(user_id, status='pending')
    in_progress_orders = get_orders_for_customer(user_id)

    if not in_progress_orders and not pending_orders:
        with ui.row().classes("justify-center w-full mt-4"):
            ui.label(t("no_in_progress_orders", lang_cookie)).classes("text-lg text-center")
    else:
        with ui.row().classes("justify-center w-full mt-4"):
            ui.label(t("my_in_progress_orders", lang_cookie)).classes("text-2xl font-bold text-center mt-4")

        
        with ui.row().classes('w-full flex justify-center mt-6'):

            with ui.column().classes("w-full lg:w-1/3 gap-4 h-[calc(100vh-8rem)] items-center pr-2"):

                ui.label(t("pending_orders", lang_cookie)).classes("text-lg text-center font-semibold")

                with ui.column().classes("w-full overflow-y-auto"):

                    for order in pending_orders:
                        order_id = order['order_id']
                        with ui.card().classes("w-full mt-4 bg-yellow-100 text-yellow-800 cursor-pointer") \
                                .on('click', lambda e, oid=order_id: ui.navigate.to(f'/orders_in_progress/{oid}')):
                            ui.label(f"{t('commande_num', lang_cookie)}{order_id}").classes("font-bold")
                            ui.label(t("pending_order", lang_cookie))
                            ui.label(f"{t('delivery_address', lang_cookie)}{order['address']}")
                            if order.get('address_details'):
                                ui.label(f"{t('additional_details', lang_cookie)}{order['address_details']}")
                            if order.get('order_code'):
                                ui.label(f"{t('order_code', lang_cookie)}{order['order_code']}").classes("mt-2")
                            ui.label(f"{t('delivery_cost', lang_cookie)}{order['delivery_cost']:.2f}€").classes("mt-4")
                            ui.label(f"{t('total_cost', lang_cookie)}{order['total']:.2f}€").classes("font-bold mt-2")

            with ui.column().classes("w-full lg:w-1/3 gap-4 h-[calc(100vh-8rem)] items-center pr-2"):

                ui.label(t("in_progress_orders", lang_cookie)).classes("text-lg text-center font-semibold")

                with ui.column().classes("w-full overflow-y-auto"):

                    for order in in_progress_orders:
                        order_id = order['order_id']
                        with ui.card().classes("w-full mt-4 bg-green-100 text-green-800 cursor-pointer") \
                                .on('click', lambda e, oid=order_id: ui.navigate.to(f'/orders_in_progress/{oid}')):
                            ui.label(f"{t('commande_num', lang_cookie)}{order_id}").classes("font-bold")
                            ui.label(f"{t('delivery_person_name', lang_cookie)}{order['delivery_person']}")
                            ui.label(f"{t('delivery_address', lang_cookie)}{order['address']}")
                            if order.get('address_details'):
                                ui.label(f"{t('additional_details', lang_cookie)}{order['address_details']}")
                            if order.get('order_code'):
                                ui.label(f"{t('order_code', lang_cookie)}{order['order_code']}").classes("mt-2")
                            ui.label(f"{t('delivery_cost', lang_cookie)}{order['delivery_cost']:.2f}€").classes("mt-4")
                            ui.label(f"{t('total_cost', lang_cookie)}{order['total']:.2f}€").classes("font-bold mt-2")
