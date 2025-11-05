from nicegui import ui, app
from fastapi.responses import RedirectResponse
import uuid
from fastapi import Request
from urllib.parse import parse_qs, urlparse, quote, unquote
from collections import defaultdict
import time
import smtplib
from email.mime.text import MIMEText
import random
import string
import os
from dotenv import load_dotenv
import base64


from app.components.theme import apply_background
from app.components.navbar import navbar
from app.services.auth import sessions, logout
from app.services.users import get_connection, add_user, get_user_info, get_id_from_username, confirm_user, add_code_user, verify_user_code
from app.services.settings import get_setting
from app.security.passwords import verify_password
from app.translations.translations import t

from app.services.file_io import load_yaml
functionalities_switch = load_yaml('components/functionalities_switch.yaml')
ENABLE_MIN_PASSWORD_LENGHT = functionalities_switch.get('ENABLE_MIN_PASSWORD_LENGHT', True)
EMAIL_CONFIRMATION_SIGN_UP_ENABLED = functionalities_switch.get('EMAIL_CONFIRMATION_SIGN_UP_ENABLED', True)


login_attempts = defaultdict(list)  # Dictionnaire global : { ip_ou_username: [timestamps_des_essais] }
email_resend = defaultdict(list)  # Dictionnaire global : { ip_ou_username: [timestamps_des_envois] }

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))


@ui.page('/')
def login_page(request: Request):

    """Page de connexion et d'inscription."""

    # Application du style global et de la barre de navigation
    apply_background()
    navbar(request)

    lang_cookie = request.cookies.get("language", "fr")

    # Paramètre pour notify récupérés dans l’URL
    query_params = parse_qs(urlparse(str(request.url)).query)
    notify_key = query_params.get("notify", [None])[0]

    if notify_key:
        ui.notify(
            t(notify_key, lang_cookie),
            color='negative',
            position='top',
            close_button=True
        )

    # === Formulaire de connexion ===
    with ui.column().classes('items-center justify-center w-96 mx-auto glass-card fade-in p-6 mt-10 mb-10'):

        ui.label(t("login", lang_cookie)).classes('text-2xl font-bold text-black mb-4')
        username = ui.input(t("username", lang_cookie)).classes('w-full mb-2')
        password = ui.input(t("password", lang_cookie), password=True, password_toggle_button=True).classes('w-full mb-4')
        login_warning = ui.label(t("password_caps", lang_cookie)).classes('text-red-600 text-sm mb-3 hidden')

        # Bouton qui redirige vers une route qui gère le login
        def handle_login():

            password_value = password.value
            username_value = username.value
            encoded_password = quote(base64.urlsafe_b64encode(password_value.encode()).decode())

            ui.navigate.to(f"/do_login?u={username_value}&p={encoded_password}")

        ui.button(t("connect", lang_cookie), on_click=handle_login) \
            .classes('btn-auth w-full mb-2')

        ui.separator()
        ui.label(t("no_account", lang_cookie)).classes('text-lg font-bold text-black mt-2 mb-2')
        email = ui.input(t("email", lang_cookie)).classes('w-full mb-2').props('required')
        signup_user = ui.input(t("username", lang_cookie)).classes('w-full mb-2').props('required')
        signup_pass = ui.input(t("password", lang_cookie), password=True, password_toggle_button=True).classes('w-full mb-4').props('required')
        signup_warning = ui.label(t("password_caps", lang_cookie)).classes('text-red-600 text-sm mb-3 hidden')

        # Warning quand majuscule sur la saisie du mot de passe
        ui.run_javascript("""
            const fields = [
                {input: document.querySelectorAll('input[type="password"]')[0], warning: document.querySelectorAll('.text-red-600.text-sm')[0]},
                {input: document.querySelectorAll('input[type="password"]')[1], warning: document.querySelectorAll('.text-red-600.text-sm')[1]},
            ];

            let capsLockOn = false;
            let activeField = null;

            // Vérifie CapsLock à chaque frappe
            document.addEventListener('keydown', e => {
                if (e.getModifierState && e.getModifierState('CapsLock')) {
                    capsLockOn = true;
                } else {
                    capsLockOn = false;
                }
                updateWarnings();
            });

            document.addEventListener('keyup', e => {
                if (e.getModifierState && e.getModifierState('CapsLock')) {
                    capsLockOn = true;
                } else {
                    capsLockOn = false;
                }
                updateWarnings();
            });

            // Quand un champ est sélectionné
            fields.forEach(f => {
                if (f.input) {
                    f.input.addEventListener('focus', () => {
                        activeField = f;
                        updateWarnings();
                    });
                    f.input.addEventListener('blur', () => {
                        f.warning.classList.add('hidden');
                        activeField = null;
                    });
                }
            });

            function updateWarnings() {
                fields.forEach(f => {
                    if (f === activeField && capsLockOn) {
                        f.warning.classList.remove('hidden');
                    } else {
                        f.warning.classList.add('hidden');
                    }
                });
            }
        """)

        # === Fonction d'inscription ===
        def handle_signup():

            """Inscription d'un utilisateur via le formulaire UI."""

            username_value = signup_user.value.strip()
            email_value = email.value.strip()
            password_value = signup_pass.value.strip()

            if not username_value or not email_value or not password_value:
                ui.notify(t("mandatory_fields", lang_cookie), color='negative')
                return
            
            if len(username_value) > 30 or len(email_value) > 50 or len(password_value) > 50:
                ui.notify(t("too_long", lang_cookie), color='negative')
                return
            
            if ENABLE_MIN_PASSWORD_LENGHT: 
                min_lenght_password = get_setting("password_policy_min_length", 8)
                if len(password_value) < min_lenght_password:
                    ui.notify(f"{t('password_lenght', lang_cookie)}{min_lenght_password}{t('password_lenght_2', lang_cookie)}", color='negative')
                    return

            res_add_user = add_user(username_value, password_value, email_value)
            if res_add_user[0] and res_add_user[1]:
                ui.notify(t("signup_success", lang_cookie), color='positive')

                if EMAIL_CONFIRMATION_SIGN_UP_ENABLED:
                    # === Popup de confirmation ===
                    dialog_confirm = ui.dialog()
                    with dialog_confirm, ui.card().classes("p-6 w-80"):
                        ui.label(t("enter_confirmation_code", lang_cookie)).classes("text-lg font-bold mb-4")
                        ui.label(t("code_sent_by_mail", lang_cookie))
                        code_input = ui.input(t("confirmation_code", lang_cookie)).classes("w-full mb-4")

                        def send_confirmation_email(to_email, code):

                            site_name = get_setting("site_name", "")
                            subject = f"{t('confirmation_code', lang_cookie)} {site_name}"
                            body = f"{t('your_code_is', lang_cookie)}{code}"

                            msg = MIMEText(body)
                            msg['Subject'] = subject
                            msg['From'] = "noreply@pharmalink.com"
                            msg['To'] = to_email

                            # Exemple avec SMTP Gmail
                            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
                                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                                try:
                                    server.send_message(msg)
                                    return True
                                except:
                                    ui.notify(t("email_not_valid", lang_cookie), color='negative')
                                    return False

                        def generate_confirmation_code(length=5):

                            """Génère un code alphanumérique pour confirmation par email"""

                            return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

                        # Déclencher l'envoi du code par email)
                        def send_code():

                            if not email_value:
                                ui.notify(t("enter_email", lang_cookie), color="red")
                                return False
                            
                            code = generate_confirmation_code()

                            if send_confirmation_email(email_value, code):
                                user_id = get_id_from_username(signup_user.value.strip())
                                add_code_user(user_id, code)
                                ui.notify(f"{t('confirmation_code_sent', lang_cookie)}{email_value}", color="green")
                                return True
                            else:
                                return False

                        def resend_code():

                            # Vérifie la limite d’essais
                            client_id = request.client.host or username_value
                            now = time.time()
                            window = 60  # 1 minute
                            max_attempts = 1

                            # Nettoie les anciens essais
                            email_resend[client_id] = [ts for ts in email_resend[client_id] if now - ts < window]

                            # Test si on dépasse le nombre d'essais
                            if len(email_resend[client_id]) >= max_attempts:
                                ui.notify(t('too_many_attempts', lang_cookie), color='negative')
                            else:
                                send_code()
                                email_resend[client_id].append(now)

                        def verify_code():

                            """Vérification du code de confirmation."""

                            code_entered = code_input.value.strip()
                            user_id = get_id_from_username(signup_user.value.strip())

                            if verify_user_code(user_id, code_entered): #== "00000":
                                confirm_user(user_id)
                                ui.notify(t("account_confirmed", lang_cookie), color='positive')
                                dialog_confirm.close()

                                encoded_password = quote(base64.urlsafe_b64encode(password_value.encode()).decode())
                                ui.navigate.to(f"/do_login?u={username_value}&p={encoded_password}")

                            else:
                                ui.notify(t("invalid_code", lang_cookie), color='negative')

                        with ui.row().classes("justify-end gap-3"):
                            ui.button(t("cancel", lang_cookie), on_click=dialog_confirm.close)
                            ui.button(t("validate", lang_cookie), on_click=verify_code)
                            ui.button(t('resend_code', lang_cookie), on_click=resend_code)

                    # 🔔 Ouvre la popup de confirmation
                    dialog_confirm.open()

                    if not send_code():
                        dialog_confirm.close()
                
                else:  # email confirmation disabled
                    user_id = get_id_from_username(signup_user.value.strip())
                    confirm_user(user_id)
                    encoded_password = quote(base64.urlsafe_b64encode(password_value.encode()).decode())
                    ui.navigate.to(f"/do_login?u={username_value}&p={encoded_password}")


            elif not res_add_user[0] and not res_add_user[1]:
                ui.notify(t("user_&_email_exists", lang_cookie), color='negative')
            elif not res_add_user[0]:
                ui.notify(t("user_exists", lang_cookie), color='negative')
            else:
                ui.notify(t("email_exists", lang_cookie), color='negative')

        ui.button(t("signup", lang_cookie), on_click=handle_signup).classes('btn-auth w-full')


# === Route spéciale login qui met le cookie avant envoi de la page ===
@ui.page('/do_login')
def do_login(u: str, p: str, request: Request):

    """Gère la connexion utilisateur avec la DB SQL et crée une session."""

    lang_cookie = request.cookies.get("language", "fr")
    
    # Decoding password
    p = base64.urlsafe_b64decode(unquote(p)).decode()

    # Vérifie la limite d’essais
    client_id = request.client.host or u
    now = time.time()
    window = 60  # 1 minute
    max_attempts = 3

    # Nettoie les anciens essais
    login_attempts[client_id] = [ts for ts in login_attempts[client_id] if now - ts < window]

    # Test si on dépasse le nombre d'essais
    if len(login_attempts[client_id]) >= max_attempts:
        return RedirectResponse('/?notify=too_many_attempts')

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, password FROM users WHERE username = ?", (u,))
        row = cursor.fetchone()

    if not row:
        return RedirectResponse('/?notify=bad_credentials')

    user_info = get_user_info(row[0])

    if verify_password(p, row[1]):
        
        # Token crée avant le check de status confirmé (à améliorer)
        token = str(uuid.uuid4())
        sessions[token] = row[0]   # user_id stocké dans le token de session
        app.storage.browser['token'] = token  # stockage local
        
        # Login des livreurs
        if user_info.get('is_confirmed', False) and user_info.get('is_delivery_person', False) and not user_info.get('is_admin', False):
            return RedirectResponse('/delivery/home')
        
        # Login des utilisateurs
        if user_info.get('is_confirmed', False) or user_info.get('is_admin', False):
            return RedirectResponse('/home')
        
        else:
            if EMAIL_CONFIRMATION_SIGN_UP_ENABLED:
                with ui.dialog() as dialog_confirm:
                    with ui.card().classes("p-6 w-80"):
                        ui.label(t("enter_confirmation_code", lang_cookie)).classes("text-xl font-bold mb-4")
                        ui.label(t("code_sent_by_mail", lang_cookie))
                        code_input = ui.input(t("confirmation_code", lang_cookie)).classes("w-full mb-4")

                        def validate_code():

                            """Validation du code de confirmation."""

                            code_entered = code_input.value.strip()
                            
                            user_id = row[0]
                            if verify_user_code(user_id, code_entered):  # if code_entered == "00000":
                                confirm_user(user_id)
                                ui.notify(t("account_confirmed", lang_cookie), color="positive")
                                dialog_confirm.close()

                                if user_info.get('is_delivery_person', False):
                                    ui.navigate.to('/delivery/home')
                                else:
                                    ui.navigate.to("/home")

                            else:
                                ui.notify(t("invalid_code", lang_cookie), color="negative")

                        def send_confirmation_email(to_email, code):

                            site_name = get_setting("site_name")
                            subject = f"{t('confirmation_code', lang_cookie)} {site_name}"
                            body = f"{t('your_code_is', lang_cookie)}{code}"

                            msg = MIMEText(body)
                            msg['Subject'] = subject
                            msg['From'] = "noreply@pharmalink.com"
                            msg['To'] = to_email

                            # Exemple avec SMTP Gmail
                            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
                                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                                try:
                                    server.send_message(msg)
                                    return True
                                except:
                                    ui.notify(t("email_not_valid", lang_cookie), color='negative')
                                    return False

                        def generate_confirmation_code(length=5):

                            """Génère un code alphanumérique pour confirmation par email"""

                            return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

                        # Déclencher l'envoi du code par email)
                        def send_code():

                            if not user_info['email']:
                                ui.notify("Veuillez saisir un email", color="red")
                                return False
                            
                            code = generate_confirmation_code()

                            if send_confirmation_email(user_info['email'], code):
                                user_id = get_id_from_username(u)
                                add_code_user(user_id, code)
                                ui.notify(f"Un code de confirmation a été envoyé à {user_info['email']}", color="green")
                                return True
                            else:
                                return False

                        def resend_code():

                            # Vérifie la limite d’essais
                            client_id = request.client.host or u
                            now = time.time()
                            window = 60  # 1 minute
                            max_attempts = 1

                            # Nettoie les anciens essais
                            email_resend[client_id] = [ts for ts in email_resend[client_id] if now - ts < window]

                            # Test si on dépasse le nombre d'essais
                            if len(email_resend[client_id]) >= max_attempts:
                                ui.notify(t('too_many_attempts', lang_cookie), color='negative')
                            else:
                                send_code()
                                email_resend[client_id].append(now)

                        def cancel():

                            """Annulation de la connexion."""

                            dialog_confirm.close()
                            ui.navigate.to('/?notify=login_cancelled')

                        with ui.row().classes("justify-end gap-3"):
                            ui.button(t("cancel", lang_cookie), on_click=cancel)
                            ui.button(t("validate", lang_cookie), on_click=validate_code)
                            ui.button(t('resend_code', lang_cookie), on_click=resend_code)

                dialog_confirm.open()
                return
            
            else:
                user_id = row[0]
                confirm_user(user_id)
                if user_info.get('is_delivery_person', False):
                    ui.navigate.to('/delivery/home')
                else:
                    ui.navigate.to("/home")

    else:
        # Enregistre cette tentative échouée
        login_attempts[client_id].append(now)

        return RedirectResponse('/?notify=bad_credentials')


@ui.page('/logout')
def logout_page():
    return logout()