from nicegui import ui, app
from fastapi.responses import RedirectResponse
import datetime
from fastapi import Request

from services.auth import get_current_user
from components.navbar import navbar
from components.footer import footer_bar
from components.theme import apply_background
from services.users import get_user_info
from services.settings import get_setting, set_setting
from services.logging_setup import get_logger
from translations.translations import t


@ui.page('/admin/settings')
def admin_settings(request: Request):

    """Page de gestion des paramètres pour les administrateurs."""

    # === Setup initial ===

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for admin page settings: no valid token, ip: {host}")
        return RedirectResponse('/')
    
    # Vérification des droits admin
    user_info = get_user_info(user_id)
    if not user_info.get('is_admin', False):
        logger_user = get_logger('nav')
        logger_user.info(f"Tried to open settings page but was denied", extra={"user_id": user_id})
        return RedirectResponse('/home')
    
    apply_background()
    navbar(request)
    footer_bar(request)

    logger = get_logger('admin')
    logger.info("Settings page consulted", extra={"admin_user_id": user_id})

    lang_cookie = request.cookies.get("language", "fr")

    # Bouton retour
    with ui.row().classes('w-full p-4 sticky top-0 left-0 z-50 bg-transparent justify-start'):
        ui.button('⬅', on_click=lambda: ui.run_javascript('window.history.back()')) \
            .props('unelevated') \
            .classes('btn-back shadow-lg')

    # === Contenu ===
    with ui.column().classes('items-center w-full max-w-6xl mx-auto p-8 gap-10'):

        # === Titre ===
        ui.label(t("site_parameters", lang_cookie)).classes('text-4xl font-extrabold text-center mb-6')

        # === Paramètres administratifs ===
        with ui.card().classes("w-full p-6 bg-white shadow-md rounded-xl"):
            
            site_name_input = ui.input(t("site_name", lang_cookie), value=get_setting("site_name")).classes("w-full")
            site_version_input = ui.input(t("site_version", lang_cookie), value=get_setting("site_version")).classes("w-full")
            # NOT USED
            site_logo_input = ui.input(t("logo_url", lang_cookie), value=get_setting("site_logo")).classes("w-full")
            # NOT USED
            site_theme_input = ui.input(t("theme_color", lang_cookie), value=get_setting("site_theme")).classes("w-full")
            # NOT USED
            admin_email_input = ui.input(t("admin_email", lang_cookie), value=get_setting("admin_email")).classes("w-full")
            support_email_input = ui.input(t("support_email", lang_cookie), value=get_setting("support_email")).classes("w-full")
            password_policy_input = ui.input(t("min_password_lenght", lang_cookie), value=get_setting("password_policy_min_length")).props("type=number step=1 min=1").classes("w-full")
            # NOT USED
            default_currency_input = ui.input(t("default_currency", lang_cookie), value=get_setting("default_currency")).classes("w-full")
            items_per_page_input = ui.input(t("products_per_page", lang_cookie), value=get_setting("display_items_per_page")).props("type=number step=1 min=1").classes("w-full")
            # NOT USED
            free_delivery_input = ui.input(t("free_delivery_threshold", lang_cookie), value=get_setting("free_delivery_threshold")).props("type=number").classes("w-full")
            support_phone_input = ui.input(t("support_phone", lang_cookie), value=get_setting("support_phone")).classes("w-full")
            max_order_delivery = ui.input(t("max_order_delivery", lang_cookie), value=get_setting("max_order_delivery")).props("type=number step=1 min=1").classes("w-full")
            # NOT USED
            guest_checkout_input = ui.checkbox(t("allow_guest_checkout", lang_cookie), value=get_setting("allow_guest_checkout")).classes("w-full")
            show_notifications_input = ui.checkbox(t("show_notifications", lang_cookie), value=get_setting("show_notifications")).classes("w-full")   
            user_registration_input = ui.checkbox(t("allow_user_registration", lang_cookie), value=get_setting("allow_user_registration")).classes("w-full")
            # TO IMPROVE (logout sur toutes les pages à ajouter)
            maintenance_mode_input = ui.checkbox(t("maintenance_mode", lang_cookie), value=get_setting("maintenance_mode")).classes("w-full")         

            def save_settings():

                """Sauvegarde les paramètres modifiés."""

                inputs = [("site_name", site_name_input), 
                          ("site_version", site_version_input), 
                          ("site_logo", site_logo_input),
                          ("site_theme", site_theme_input),
                          ("admin_email", admin_email_input),
                          ("support_email", support_email_input),
                          ("password_policy_min_length", password_policy_input),
                          ("allow_user_registration", user_registration_input),
                          ("maintenance_mode", maintenance_mode_input),
                          ("default_currency", default_currency_input),
                          ("display_items_per_page", items_per_page_input),
                          ("free_delivery_threshold", free_delivery_input),
                          ("allow_guest_checkout", guest_checkout_input),
                          ("support_phone", support_phone_input),
                          ("show_notifications", show_notifications_input),
                          ("max_order_delivery", max_order_delivery)
                         ]

                for key, input_widget in inputs:
                    value = input_widget.value
                    if isinstance(value, bool):
                        value = int(value)  # stocker les booléens comme 0/1
                    set_setting(key, value)

                logger.info(f"Site settings updated", extra={"admin_user_id": user_id})
                ui.notify(t("parameters_updated", lang_cookie), color="positive")


            ui.button(t("save_2", lang_cookie), on_click=save_settings).classes(
                "bg-blue-500 text-white px-6 py-2 rounded-lg hover:bg-blue-600 mt-4"
            )