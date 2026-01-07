from nicegui import ui
from fastapi.responses import RedirectResponse
from fastapi import Request

from services.auth import get_current_user
from services.users import get_len_panier, get_wallet_balance, get_user_from_id, get_user_info, get_in_progress_orders_count
from services.settings import get_setting
from translations.translations import t


def navbar(request: Request):

    """Affiche une barre de navigation si l'utilisateur est connecté. Utilisée pour les utilisateurs clients."""


    # Création de class CSS pour gestion de l'affichage en fonction de la taille de l'écran
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

    # user_id = get_current_user()
    
    user_id = get_current_user(request)
    if user_id:
        user_info = get_user_info(user_id)


    # === Contenu de la navbar ===

    with ui.header().classes('app-navbar items-center justify-between px-4 py-3 shadow-md'):

        with ui.row().classes('items-center gap-3'):

            # === Nom et logo ===
            site_name = get_setting("site_name")
            ui.button(f'🏥 {site_name}', on_click=lambda: ui.navigate.to('/home')) \
                .props("color='' unelevated") \
                .classes('nav-brand text-lg') \
                .style('background: transparent; cursor: pointer;')
            
            # === Avatar sur petit écran seulement ===
            if user_id and (user_info.get('is_confirmed', False) or user_info.get('is_admin', False)):  # Seulement si l'utilisateur est confirmé ou admin
                username = get_user_from_id(user_id)
                with ui.row().classes('flex md:hidden items-center gap-3'):  # md:hidden -> cache sur écran large
                    ui.image(f"https://ui-avatars.com/api/?name={username}&background=34a853&color=fff&size=128") \
                        .classes('nav-avatar')
                    
                    ui.label(username) \
                    .props("color='' unelevated") \
                    .classes('nav-username')

                # === Admin panel ===
                with ui.row().classes('items-center gap-3 desktop-nav'):  # desktop-nav: seulement sur écran large
                    if user_info.get('is_admin', False):
                        ui.button(t('admin_panel', lang_cookie), on_click=lambda: ui.navigate.to('/admin_panel')) \
                            .props("color='' unelevated") \
                            .classes('nav-btn nav-wallet')
                        
                        ui.button(t('view_delivery', lang_cookie), on_click=lambda: ui.navigate.to('/delivery/home')) \
                            .props("color='' unelevated") \
                            .classes('nav-btn nav-wallet')
                
        # === Zone utilisateur ===
        if user_id and (user_info.get('is_confirmed', False) or user_info.get('is_admin', False)):
            username = get_user_from_id(user_id)

            # === Section écran large ===
            with ui.row().classes('items-center gap-3 desktop-nav'):  # desktop-nav: seulement sur écran large

                # === Avatar ===
                ui.image(f"https://ui-avatars.com/api/?name={username}&background=34a853&color=fff&size=128") \
                    .classes('nav-avatar')
                
                # === Nom utilisateur ===
                ui.label(username) \
                    .props("color='' unelevated") \
                    .classes('nav-username')
                
                # === Wallet ===
                wallet_balance = get_wallet_balance(user_id)
                ui.button(f'💳 {wallet_balance:.2f} €',
                          on_click=lambda: ui.navigate.to('/wallet')) \
                    .props("color='' unelevated") \
                    .classes('nav-btn nav-wallet')
                
                # === Commandes ===
                orders_in_progress = get_in_progress_orders_count(user_id)

                with ui.button(on_click=lambda: ui.navigate.to('/orders_in_progress')) \
                        .props("color='' unelevated") \
                        .classes('nav-btn nav-orders'):
                    if orders_in_progress > 0:
                        ui.label(str(orders_in_progress)).classes('nav-badge')
                    ui.icon('local_shipping')

                # === Panier ===
                items_in_panier = get_len_panier(user_id)
                with ui.button(on_click=lambda: ui.navigate.to('/panier')) \
                        .props("color='' unelevated") \
                        .classes('nav-btn nav-cart'):
                    if items_in_panier > 0:
                        ui.label(str(items_in_panier)).classes('nav-badge')
                    ui.icon('shopping_cart')

                # === Profil ===
                ui.button('', on_click=lambda: ui.navigate.to('/profile'), icon='person') \
                    .props("color='' unelevated") \
                    .classes('nav-profile')

                # === Bouton changer la langue ===
                with ui.button(icon='language').props("color='' unelevated").classes('nav-btn nav-settings'):
                    
                    language_dict = {"fr": "Français", "en": "English"}

                    def change_lang(lang):

                        ui.run_javascript(
                            f'''
                            // Met à jour le cookie
                            document.cookie = "language={lang}; path=/; max-age={60*60*24*30}";
                            // Recharge la page pour appliquer la langue
                            window.location.reload();
                            '''
                        )
                        ui.notify(f"{t('lang_changed', lang_cookie)} {language_dict[lang]}")

                    with ui.menu() as menu:
                        for lang, lang_label in language_dict.items():
                            ui.menu_item(lang_label, on_click=lambda l=lang: change_lang(l))

                # === Déconnexion ===
                ui.button('', on_click=lambda: ui.navigate.to('/logout'), icon='logout') \
                    .props("color='' unelevated") \
                    .classes('nav-btn nav-danger')
                

            # === Section petit écran (mobile) ===
            with ui.row().classes('flex md:hidden items-center gap-3'):

                # === Wallet ===
                wallet_balance = get_wallet_balance(user_id)
                ui.button(f'💳 {wallet_balance:.2f} €',
                          on_click=lambda: ui.navigate.to('/wallet')) \
                    .props("color='' unelevated") \
                    .classes('nav-btn nav-wallet')
                
                # === Commandes ===
                orders_in_progress = get_in_progress_orders_count(user_id)

                with ui.button(on_click=lambda: ui.navigate.to('/orders_in_progress')) \
                        .props("color='' unelevated") \
                        .classes('nav-btn nav-orders'):
                    if orders_in_progress > 0:
                        ui.label(str(orders_in_progress)).classes('nav-badge')
                    ui.icon('local_shipping')

                # === Panier ===
                items_in_panier = get_len_panier(user_id)
                with ui.button(on_click=lambda: ui.navigate.to('/panier')) \
                        .props("color='' unelevated") \
                        .classes('nav-btn nav-cart'):
                    if items_in_panier > 0:
                        ui.label(str(items_in_panier)).classes('nav-badge')
                    ui.icon('shopping_cart')

                # === Profil ===
                ui.button('', on_click=lambda: ui.navigate.to('/profile'), icon='person') \
                    .props("color='' unelevated") \
                    .classes('nav-profile')
                
                # === Choix de la langue (popup appelée dans bouton paramètres) ===
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
                        if user_info.get('is_admin', False):
                            # Admin panel et switch livreur/client dans paramètres sur mobile
                            ui.menu_item(t('admin_panel', lang_cookie), on_click=lambda: ui.navigate.to('/admin_panel'))
                            ui.menu_item(t('view_delivery', lang_cookie), on_click=lambda: ui.navigate.to('/delivery/home'))
                        ui.menu_item(t("lang_choice", lang_cookie), on_click=lambda: dialog_language.open())
                        ui.menu_item(t('logout', lang_cookie), on_click=lambda: ui.navigate.to('/logout'))


        # === Changer la langue même quand utilisateur pas défini (au login) ===
        else:
            with ui.row().classes('items-center gap-3'):
                with ui.button(icon='language').props("color='' unelevated").classes('nav-btn nav-settings'):
                        
                        language_dict = {"fr": "Français", "en": "English"}

                        def change_lang(lang):

                            ui.run_javascript(
                                f'''
                                // Met à jour le cookie
                                document.cookie = "language={lang}; path=/; max-age={60*60*24*30}";
                                // Recharge la page pour appliquer la langue
                                window.location.reload();
                                '''
                            )
                            ui.notify(f"{t('lang_changed', lang_cookie)} {language_dict[lang]}")

                        with ui.menu() as menu:
                            for lang, lang_label in language_dict.items():
                                ui.menu_item(lang_label, on_click=lambda l=lang: change_lang(l))