from nicegui import ui, app
from fastapi.responses import RedirectResponse
from fastapi import Request

from services.auth import get_current_user, sessions
from components.navbar import navbar
from components.footer import footer_bar
from components.theme import apply_background
from services.users import get_user_info
from services.logging_setup import get_logger
from translations.translations import t


@ui.page('/admin_panel')
def admin_panel(request: Request):

    """Page d'administration pour les utilisateurs avec les droits admin."""

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    
    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for admin page admin panel: no valid token, ip: {host}")
        return RedirectResponse('/')    
    
    # Vérification des droits admin
    user_info = get_user_info(user_id)
    if not user_info.get('is_admin', False):
        logger_user = get_logger('nav')
        logger_user.info(f"Tried to open admin panel page but was denied", extra={"user_id": user_id})
        return RedirectResponse('/home')
    
    apply_background()
    navbar(request)
    footer_bar(request)

    lang_cookie = request.cookies.get("language", "fr")

    logger = get_logger('admin')
    logger.info("Admin panel page consulted", extra={"admin_user_id": user_id})

    # === Contenu de la page ===
    
    with ui.column().classes('items-center w-full max-w-4xl mx-auto p-8 gap-8'):
        
        # Titre
        ui.label(t("admin_panel_2", lang_cookie)).classes(
            'text-4xl font-extrabold text-center'
        )

        # Description
        ui.label(
            t("admin_panel_desc", lang_cookie)
        ).classes('text-lg text-gray-600 text-center max-w-2xl')

        # Séparateur visuel
        ui.separator().classes('my-4 w-2/3')

        # Grille des options d'administration
        with ui.grid(columns=2).classes('gap-8 w-full'):
            ui.button(t("handle_users", lang_cookie),
                    on_click=lambda: ui.navigate.to('/admin/users')) \
            .classes("admin-action admin-action--blue")

            ui.button(t("handle_products", lang_cookie),
                    on_click=lambda: ui.navigate.to('/admin/products')) \
            .classes("admin-action admin-action--green")

            ui.button(t("handle_pharmacies", lang_cookie),
                    on_click=lambda: ui.navigate.to('/admin/pharmacies')) \
            .classes("admin-action admin-action--purple")

            ui.button(t("order_management", lang_cookie),
                    on_click=lambda: ui.navigate.to('/admin/orders')) \
            .classes("admin-action admin-action--red")

            ui.button(t("site_analytics", lang_cookie),
                    on_click=lambda: ui.navigate.to('/admin/analytics')) \
                .classes("admin-action admin-action--yellow w-auto")

            ui.button(t("site_settings", lang_cookie),
                    on_click=lambda: ui.navigate.to('/admin/settings')) \
                .classes("admin-action admin-action--gray w-auto")