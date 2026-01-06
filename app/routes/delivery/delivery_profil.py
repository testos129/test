from nicegui import ui, app
from fastapi import Request
from fastapi.responses import RedirectResponse

from components.theme import apply_background
from components.navbar_delivery import navbar_delivery
from components.footer import footer_bar
from services.auth import get_current_user
from services.users import get_user_info, update_user, get_orders_for_delivery_person
from security.passwords import hash_password
from services.distance import distance_by_day
from services.geolocation import start_geolocation_tracking
from services.logging_setup import get_logger
from translations.translations import t


@ui.page("/delivery/profil")
def delivery_profil(request: Request):

    """ Page de profil du livreur."""

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for delivery page profil: no valid token, ip: {host}")
        return RedirectResponse('/')

    user_info = get_user_info(user_id)
    if not user_info.get('is_admin', False):
        if not user_info.get('is_confirmed', False) or not user_info.get('is_delivery_person', False):  # utilisateur non confirmé ou non livreur
            logger_user = get_logger('nav')
            logger_user.info(f"Tried to open delivery profil page but was denied", extra={"user_id": user_id})
            return RedirectResponse('/')
    
    # Styles globaux + navbar + cookies
    apply_background()
    navbar_delivery(request)
    footer_bar(request)

    lang_cookie = request.cookies.get("language", "fr")
    distance_cookie = float(request.cookies.get("max_distance", distance_by_day()))

    logger = get_logger('delivery')

    # Lance la récupération en continue de la géolocalisation
    start_geolocation_tracking(user_id)

    # === Contenu de la page ===

    # Retour à l'accueil livreur 
    with ui.row().classes('w-full p-4 sticky top-0 left-0 z-50 bg-transparent'):
        ui.button('⬅', on_click=lambda: ui.run_javascript('window.history.back()')) \
            .props('unelevated') \
            .classes('btn-back shadow-lg')
        
    # === Récupération des informations utilisateur ===
    current_email = user_info.get('email', '')
    current_phone = user_info.get('phone_number', '')
        

    # === Card principale ===
    with ui.card().classes('w-full max-w-3xl m-auto p-6 glass-card fade-in mt-6'):

        # === En-tête profil ===
        with ui.row().classes('w-full justify-center mt-2'):
            ui.label(t("profil", lang_cookie)).classes('text-3xl font-bold text-black text-center')


        # === Section 1 : Informations de base ===
        with ui.expansion(icon='home', text=t("basic_info", lang_cookie), value=False).classes('w-full bg-white/90 rounded-xl shadow-md mt-4'):

            # === Distance max ===
            distance_input = ui.number("Distance maximale (km)", value=distance_cookie).props("outlined").classes("w-full mb-4")
            
            # === Numéro de téléphone ===
            phone_number = ui.input(t("phone_number", lang_cookie), value=current_phone).classes('w-full mt-2')

            def save_changes():

                """Sauvegarde les informations renseignées en base ou dans les cookies"""
                
                # Sauvegarde max distance
                ui.run_javascript(
                    f'''document.cookie = "max_distance={distance_input.value}; path=/; max-age={60*60*24*30}";'''
                )
                new_phone = phone_number.value

                # Mise à jour en base
                update_user(
                    user_id=user_id,
                    email=None,
                    password=None,
                    phone_number=new_phone,
                )

                logger.info("User info updated", extra={"delivery_user_id": user_id})
                ui.notify(t("update_info", lang_cookie), color='positive')

            with ui.row().classes('w-full justify-center mt-4'):
                ui.button(t("save_2", lang_cookie), on_click=save_changes).classes('btn-success')


        # === Section 2 : Compte (email + mot de passe) ===
        with ui.expansion(icon='account_circle', text=t("account_info", lang_cookie)).classes('w-full bg-white/90 rounded-xl shadow-md mt-4'):

            email = ui.input(t("email", lang_cookie), value=current_email).classes('w-full mt-2')
            password = ui.input(
                t("change_password", lang_cookie),
                password=True,
                password_toggle_button=True
            ).classes('w-full mt-2')

            def save_changes_user_info():
                
                """Sauvegarde les informations renseignées en base"""

                new_email = email.value.strip() or None
                new_password = password.value.strip() or None

                if new_password:
                    pwd_hash = hash_password(new_password)
                    update_user(user_id, new_email, pwd_hash)
                else:
                    update_user(user_id, new_email, None)

                logger.info("User connection info updated", extra={"delivery_user_id": user_id})
                ui.notify(t("update_info", lang_cookie), color='positive')

            with ui.row().classes('w-full justify-center mt-4'):
                ui.button(t("save_2", lang_cookie), on_click=save_changes_user_info).classes('btn-success mt-4')


        # === Section 3 : Historique des commandes ===
        with ui.expansion(icon='shopping_bag', text=t("order_history", lang_cookie)).classes('w-full bg-white/90 rounded-xl shadow-md mt-4'):

            orders = get_orders_for_delivery_person(user_id, status='completed')

            with ui.column().classes("items-center p-6 w-full max-w-3xl m-auto fade-in"):
                ui.label(t("order_history", lang_cookie)).classes(
                    "text-3xl font-bold mb-6 text-black"
                )

                if not orders:
                    ui.label(t("no_order", lang_cookie)).classes(
                        "text-gray-500 italic"
                    )
                else:
                    for order in orders[:10]:  # Limite à 10 commandes récentes
                        with ui.card().classes(
                            "w-full bg-white/90 shadow-lg rounded-2xl p-6 mb-4 border border-gray-200 hover:shadow-xl transition-all duration-300"
                        ):
                            with ui.row().classes("justify-between items-center mb-2"):
                                ui.label(f"{t('order_number', lang_cookie)}{order['order_id']}").classes(
                                    "text-lg font-semibold text-gray-800"
                                )
                                ui.label(f"{order['date']}").classes(
                                    "text-sm text-gray-500 italic"
                                )

                            ui.label(f"{t('total', lang_cookie)}{order['total']:.2f} €").classes(
                                "font-bold text-green-600 text-lg"
                            )
        

        # === Section 4 : Aide et contact ===
        with ui.expansion(icon='help_outline', text=t("help_contact", lang_cookie)).classes(
            'w-full bg-white/90 rounded-xl shadow-md mt-4'
        ):
            
            ui.label(t("need_help", lang_cookie)).classes('text-lg font-semibold mb-2 text-center')
            ui.label(t("contact_intro", lang_cookie)).classes('text-gray-600 mb-4 text-center')

            with ui.column().classes('items-center gap-3 w-full'):
                # === Email de contact ===
                with ui.row().classes('items-center justify-center gap-2'):
                    ui.icon('email').classes('text-green-600')
                    ui.label("support@votresite.fr").classes('text-gray-700 text-base font-medium')

                # === Téléphone ===
                with ui.row().classes('items-center justify-center gap-2'):
                    ui.icon('call').classes('text-green-600')
                    ui.label("+33 0 00 00 00 00").classes('text-gray-700 text-base font-medium')

                 # === Message personnalisé ===
                ui.label(t("support_msg", lang_cookie)).classes('text-sm text-gray-500 italic mt-2 text-center')