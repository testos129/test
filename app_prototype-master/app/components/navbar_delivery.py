from nicegui import ui
from fastapi.responses import RedirectResponse
from fastapi import Request

from app.services.auth import get_current_user
from app.services.users import get_user_from_id, get_user_info
from app.services.settings import get_setting
from app.translations.translations import t


def navbar_delivery(request: Request):

    """Affiche une barre de navigation si l'utilisateur est connecté."""

    ui.add_head_html("""
        <style>
        /* Cache la navigation complète sur les écrans petits */
        @media (max-width: 768px) {
        .desktop-nav { display: none !important; }
        }

        /* Pour que le menu mobile (hamburger) s'affiche seulement sur petit écran */
        @media (min-width: 769px) {
        .mobile-nav { display: none !important; }
        }
        </style>
        """)

    lang_cookie = request.cookies.get("language", "fr")
    distance_cookie = float(request.cookies.get("max_distance", "10"))

    user_id = get_current_user()

    with ui.header().classes('app-navbar items-center justify-between px-4 py-3 shadow-md'):

        with ui.row().classes('items-center gap-3'):
            # === Nom et logo ===
            site_name = get_setting("site_name")
            ui.button(f'🏥 {site_name}', on_click=lambda: ui.navigate.to('/delivery/home')) \
                .props("color='' unelevated") \
                .classes('nav-brand text-lg') \
                .style('background: transparent; cursor: pointer;')
            
            # === Avatar sur Mobile ===
            if user_id:
                username = get_user_from_id(user_id)
                with ui.row().classes('flex md:hidden items-center gap-3'):
                    ui.image(f"https://ui-avatars.com/api/?name={username}&background=34a853&color=fff&size=128") \
                        .classes('nav-avatar')
                    
                    ui.label(username) \
                    .props("color='' unelevated") \
                    .classes('nav-username')

            # === Admin panel ===
            if user_id:
                user_info = get_user_info(user_id)
                with ui.row().classes('items-center gap-3 desktop-nav'):
                    if user_info.get('is_admin', False):
                        ui.button(t('admin_panel', lang_cookie), on_click=lambda: ui.navigate.to('/admin_panel')) \
                            .props("color='' unelevated") \
                            .classes('nav-btn nav-wallet')
                        
                        ui.button(t('view_client', lang_cookie), on_click=lambda: ui.navigate.to('/home')) \
                            .props("color='' unelevated") \
                            .classes('nav-btn nav-wallet')
                    
        
        # === Zone utilisateur ===
        if user_id:
            username = get_user_from_id(user_id)
            with ui.row().classes('items-center gap-3 desktop-nav'):

                # === Avatar ===
                ui.image(f"https://ui-avatars.com/api/?name={username}&background=34a853&color=fff&size=128") \
                    .classes('nav-avatar')
                
                # === Nom utilisateur ===
                # ui.label(f"{t('connected', lang_cookie)} : {username}") \
                ui.label(username) \
                    .props("color='' unelevated") \
                    .classes('nav-username')
                
                # === Profil ===
                ui.button('', on_click=lambda: ui.navigate.to('/delivery/profil'), icon='person') \
                    .props("color='' unelevated") \
                    .classes('nav-profile')
            
                # === Paramètres ===
                # === Filtre distance max ===
                dialog_distance = ui.dialog()
                with dialog_distance, ui.card().classes("p-6 w-80"):
                    ui.label(t("max_dist", lang_cookie)).classes("text-xl font-bold mb-4")
                    ui.label(t("max_dist_desc", lang_cookie))
                    distance_input = ui.number("Distance maximale (km)", value=distance_cookie).props("outlined").classes("w-full mb-4")
                    with ui.row().classes("justify-end gap-3"):
                        ui.button(t("cancel", lang_cookie), on_click=dialog_distance.close)
                        ui.button(
                            t("save", lang_cookie),
                            on_click=lambda: (
                                ui.notify(f"{t('distance_set', lang_cookie)} {distance_input.value} {t('km', lang_cookie)}"),
                                ui.run_javascript(
                                    f'document.cookie = "max_distance={distance_input.value}; path=/; max-age={60*60*24*30}";'
                                ),
                                dialog_distance.close()
                            )
                        )

                # === Choix de la langue ===
                dialog_language = ui.dialog()
                with dialog_language, ui.card().classes("p-6 w-80"):
                    ui.label(t("lang_choice", lang_cookie)).classes("text-xl font-bold mb-4")
                    language_dict = {"fr": "Français", "en": "English"}
                    language_select = ui.select(language_dict, value=lang_cookie, label="Langue").classes("w-full mb-4")
                    with ui.row().classes("justify-end gap-3"):
                        ui.button(t("cancel", lang_cookie), on_click=dialog_language.close)
                        ui.button(
                            t("save", lang_cookie),
                            on_click=lambda: (
                                ui.notify(f"{t('lang_changed', lang_cookie)} {language_dict[language_select.value]}"),
                                ui.run_javascript(
                                    f'''
                                    // Met à jour le cookie
                                    document.cookie = "language={language_select.value}; path=/; max-age={60*60*24*30}";
                                    // Recharge la page pour appliquer la langue
                                    window.location.reload();
                                    '''
                                ),
                                dialog_language.close()
                            )
                        )

                # === Bouton paramètres avec menu ===
                with ui.button(icon='settings').props("color='' unelevated").classes('nav-btn nav-settings'):
                    with ui.menu() as menu:
                        ui.menu_item(t("max_dist", lang_cookie), on_click=lambda: dialog_distance.open())
                        ui.menu_item(t("lang_choice", lang_cookie), on_click=lambda: dialog_language.open())
                        ui.menu_item(t("theme_toggle", lang_cookie), on_click=lambda: ui.notify("Basculer thème"))


                # === Déconnexion ===
                ui.button('', on_click=lambda: ui.navigate.to('/logout'), icon='logout') \
                    .props("color='' unelevated") \
                    .classes('nav-btn nav-danger')
                

            # === Section Mobile ===
            with ui.row().classes('flex md:hidden items-center gap-3'):

                # === Profil ===
                ui.button('', on_click=lambda: ui.navigate.to('/profile'), icon='person') \
                    .props("color='' unelevated") \
                    .classes('nav-profile')
                
                # === Bouton paramètres avec menu ===
                with ui.button(icon='settings').props("color='' unelevated").classes('nav-btn nav-settings'):
                    with ui.menu() as menu:
                        if user_info.get('is_admin', False):
                            ui.menu_item(t('admin_panel', lang_cookie), on_click=lambda: ui.navigate.to('/admin_panel'))
                            ui.menu_item(t('view_client', lang_cookie), on_click=lambda: ui.navigate.to('/home'))
                        ui.menu_item(t("max_dist", lang_cookie), on_click=lambda: dialog_distance.open())
                        ui.menu_item(t("lang_choice", lang_cookie), on_click=lambda: dialog_language.open())
                        ui.menu_item(t("theme_toggle", lang_cookie), on_click=lambda: ui.notify(t("change_theme", lang_cookie)))
                

                # === Déconnexion ===
                ui.button('', on_click=lambda: ui.navigate.to('/logout'), icon='logout') \
                    .props("color='' unelevated") \
                    .classes('nav-btn nav-danger')