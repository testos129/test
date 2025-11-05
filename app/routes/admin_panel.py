from nicegui import ui, app
from fastapi.responses import RedirectResponse
from fastapi import Request

from services.auth import get_current_user, sessions
from components.navbar import navbar
from components.theme import apply_background
from services.users import get_user_info
from translations.translations import t


@ui.page('/admin_panel')
def admin_panel(request: Request):

    """Page d'administration pour les utilisateurs avec les droits admin."""

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    if not get_current_user():
        return RedirectResponse('/')

    token = app.storage.browser.get('token')
    user_id = sessions[token]

    # user_id = get_current_user(request)
    # if not user_id:
    #     return RedirectResponse('/')
    
    # Vérification des droits admin
    user_info = get_user_info(user_id)
    if not user_info.get('is_admin', False):
        return RedirectResponse('/home')
    
    apply_background()
    navbar(request)

    lang_cookie = request.cookies.get("language", "fr")
    distance_cookie = float(request.cookies.get("max_distance", "10"))

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

            ui.button(t("site_settings", lang_cookie),
                    on_click=lambda: ui.navigate.to('/admin/settings')) \
            .classes("admin-action admin-action--gray")