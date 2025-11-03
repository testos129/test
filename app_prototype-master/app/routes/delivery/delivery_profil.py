from nicegui import ui, app
from fastapi import Request
from fastapi.responses import RedirectResponse

from components.theme import apply_background
from components.navbar_delivery import navbar_delivery
from services.auth import get_current_user, sessions
from services.users import get_user_info, update_user, get_orders_for_delivery_person
from security.passwords import hash_password
from translations.translations import t


@ui.page("/delivery/profil")
def delivery_profil(request: Request):

    """ Page de profil du livreur."""

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    if not get_current_user():
        return RedirectResponse('/')

    token = app.storage.browser.get('token')
    user_id = sessions[token]

    user_info = get_user_info(user_id)
    if not user_info.get('is_admin', False):
        if not user_info.get('is_confirmed', False) or not user_info.get('is_delivery_person', False):  # utilisateur non confirmé ou non livreur
            return RedirectResponse('/')
    
    # Styles globaux + navbar + cookies
    apply_background()
    navbar_delivery(request)

    lang_cookie = request.cookies.get("language", "fr")

    # === Contenu de la page ===
    # Retour à l'accueil livreur 
    with ui.row().classes('w-full p-4 sticky top-0 left-0 z-50 bg-transparent'):
        ui.button('⬅', on_click=lambda: ui.run_javascript('window.history.back()')) \
            .props('unelevated') \
            .classes('btn-back shadow-lg')
        
    # === Edition du profil ===
    with ui.column().classes('items-center p-6 w-full max-w-2xl m-auto glass-card fade-in'):

        # === Affichage du nom et avatar ===
        with ui.row().classes('w-full items-center justify-between'):
            # Image de profil par défaut en se basant sur le nom d'utilisateur
            ui.image(f"https://ui-avatars.com/api/?name={user_info['username']}&background=2e7d32&color=fff&size=128") \
                    .classes('rounded-full border-2 border-white shadow-md') \
                    .style('width:80px; height:80px; object-fit:cover;')
            
            ui.label(t("profil", lang_cookie)).classes('text-3xl font-bold mb-4 text-black')
        
        # === Reset de l'email ou mot de passe ===
        if user_info:
            current_email = user_info['email']
        else:
            current_email = ""


        email = ui.input(t("email", lang_cookie), value=current_email).classes('w-full')
        # Mot de passe non prérempli pour ne pas exposer l'ancien
        password = ui.input(
            t("change_password", lang_cookie),
            password=True,
            password_toggle_button=True
        ).classes('w-full')


        def save_changes():

            """Enregistre les modifications de l'email et/ou du mot de passe."""

            new_email = email.value.strip()
            new_password = password.value.strip()

            if new_password:
                # Hash du nouveau mot de passe
                pwd_hash = hash_password(new_password)
                update_user(user_id, new_email, pwd_hash)
                ui.notify(t("update_mail_password", lang_cookie), color='positive')
            else:
                # Seul l’email est mis à jour
                update_user(user_id, new_email, None)
                ui.notify(t("update_mail", lang_cookie), color='positive')


        ui.button(t("save_2", lang_cookie), on_click=save_changes).classes('btn-success mt-4')
    

    # === Affichage de l'historique des commandes ===
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