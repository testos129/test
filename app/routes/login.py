from nicegui import ui, app
from fastapi.responses import RedirectResponse, Response, JSONResponse
from fastapi import Request, Form
from fastapi import Request
from urllib.parse import parse_qs, urlparse
from collections import defaultdict
import time
import smtplib
from email.mime.text import MIMEText
import random
import string
import os
from dotenv import load_dotenv
import secrets
import hashlib

from components.theme import apply_background
from components.navbar import navbar
from services.auth import sessions, session_lock, logout
from services.users import get_connection, add_user, get_user_info, get_id_from_username, confirm_user, add_code_user, verify_user_code
from services.settings import get_setting
from security.passwords import verify_password
from services.logging_setup import get_logger
from translations.translations import t

from services.file_io import load_yaml
functionalities_switch = load_yaml('components/functionalities_switch.yaml')
ENABLE_MIN_PASSWORD_LENGHT = functionalities_switch.get('ENABLE_MIN_PASSWORD_LENGHT', True)
EMAIL_CONFIRMATION_SIGN_UP_ENABLED = functionalities_switch.get('EMAIL_CONFIRMATION_SIGN_UP_ENABLED', True)


login_attempts = defaultdict(list)  # Dictionnaire global : { ip_ou_username: [timestamps_des_essais] }
email_resend = defaultdict(list)  # Dictionnaire global : { ip_ou_username: [timestamps_des_envois] }


# Email setup
load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))


# Logger setup
logger = get_logger("auth")


# Environnement
IS_PROD = False


# ------------------------
# Helper functions
# ------------------------
def generate_token(user_id, response: Response, expiration_seconds=3600):

    """Génère un token sécurisé et le stocke dans un cookie HTTP."""

    # Token aléatoire
    raw_token = secrets.token_urlsafe(32)
    hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

    # Stockage côté serveur avec expiration
    with session_lock:
        sessions[hashed_token] = (user_id, time.time() + expiration_seconds)

    # Stockage côté client via cookie sécurisé
    response.set_cookie(
        key="token",
        value=raw_token,
        max_age=expiration_seconds,
        httponly=True,   # JS ne peut pas y accéder
        secure=IS_PROD,     # HTTPS ou non
        samesite="lax"   # protection CSRF minimale
    )

    logger.info(f"Token generated", extra={"user_id": user_id,})

    return raw_token


def send_confirmation_email(to_email, code, lang_cookie):

    """Envoi un email de confirmation"""

    site_name = get_setting("site_name", "")
    subject = f"{t('confirmation_code', lang_cookie)} {site_name}"
    body = f"{t('your_code_is', lang_cookie)}{code}"

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = "noreply@pharmalink.com"
    msg['To'] = to_email

    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        logger.warning("SMTP credentials not configured")
        return False

    # Exemple avec SMTP Gmail
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        try:
            server.send_message(msg)
            logger.info(f"Email sent to {to_email}")
            return True
        except Exception as e:
            ui.notify(t("email_not_valid", lang_cookie), color='negative')
            logger.warning(f"Can't send email to {to_email} (error: {e})")
            return False


def generate_confirmation_code(length=5):

    """Génère un code alphanumérique pour confirmation par email"""

    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def send_code(email_value, username_value, lang_cookie):

    """Déclenche l'envoi du code par email en utilisant les fonctions précédentes"""

    if not email_value:
        ui.notify(t("enter_email", lang_cookie), color="red")
        return False
    
    code = generate_confirmation_code()

    if send_confirmation_email(email_value, code, lang_cookie):
        user_id = get_id_from_username(username_value)
        add_code_user(user_id, code)
        
        logger.info(f"Confirmation code generated for user: {username_value}")
        ui.notify(f"{t('confirmation_code_sent', lang_cookie)}{email_value}", color="green")
        return True
    else:
        return False


def resend_code(request, username_value, email_value, lang_cookie):

    """Gère le renvoi du code de confirmation"""

    # Vérifie la limite d’essais
    client_id = request.client.host or username_value
    now = time.time()
    window = 60  # 1 minute
    max_attempts = 1

    # Nettoie les anciens essais
    email_resend[client_id] = [ts for ts in email_resend[client_id] if now - ts < window]

    # Test si on dépasse le nombre d'essais
    if len(email_resend[client_id]) >= max_attempts:
        logger.info(f"Max email attempts reached for user: {client_id}")
        ui.notify(t('too_many_attempts', lang_cookie), color='negative')
    else:
        logger.info(f"Resending email for user: {client_id}")
        send_code(email_value, username_value, lang_cookie)
        email_resend[client_id].append(now)


def call_login_api(lang_cookie, mode=0):

    """Call an api to do the login
    
    mode: 
        0 -> login
        1 -> signup
    """

    # On cherche les valeurs directement dans les champs pour ne pas intégrer le mot de passe dans le JS
    if mode==0:
        username_input = "username-input"
        password_input = "password-input"
    else:
        username_input = "signup-username"
        password_input = "signup-password"

    error = t("error", lang_cookie)

    ui.run_javascript(f"""
        const username = document.getElementById('{username_input}').value;
        const password = document.getElementById('{password_input}').value;
        const lang = '{lang_cookie}';

        const body = new URLSearchParams();
        body.append('u', username);
        body.append('p', password);
        body.append('lang_cookie', lang);

        fetch('/api/login', {{
            method: 'POST',
            body: body
        }})
        .then(resp => {{
            if (resp.redirected) {{
                window.location.href = resp.url;
            }} else {{
                return resp.json();
            }}
        }})
        .then(data => {{
            if (data && data.status === 'not_confirmed') {{
                alert("Votre compte n'est pas confirmé.");
            }} else if (data && data.status === 'error') {{
                alert('{error}' + data.notify);
            }}
        }})
        .catch(err => {{
            console.error('Erreur fetch login:', err);
            alert('Une erreur est survenue lors du login.');
        }});
    """)


def confirm_user_and_redirect_login(dialog_terms, user_id, lang_cookie, mode=0):

    """Effectue la confirmation de l'utilisateur et le redirige vers une route qui fait le login"""
    
    dialog_terms.close()
    confirm_user(user_id)
    logger.info(f"User confirmed", extra={"user_id": user_id})
    ui.notify(t("account_confirmed", lang_cookie), color='positive')

    call_login_api(lang_cookie, mode)


def verify_code(code_input, username_value, dialog_confirm, dialog_terms, btn_accept_terms, lang_cookie, mode):

    """Vérification du code de confirmation."""

    code_entered = code_input.value.strip()
    user_id = get_id_from_username(username_value)

    if verify_user_code(user_id, code_entered):

        logger.info(f"Confirmation code verified", extra={"user_id": user_id})    

        dialog_confirm.close()

        btn_accept_terms.on_click(lambda e: confirm_user_and_redirect_login(dialog_terms, user_id, lang_cookie, mode)) 

        dialog_terms.open()

    else:
        ui.notify(t("invalid_code", lang_cookie), color='negative')
        logger.info(f"Confirmation code entered: {code_entered} is invalid", extra={"user_id": user_id})


def confirmation_process(username_value, email_value, request, lang_cookie, mode):

    """Process de confirmation par email (si activé), puis validation des conditions générales"""

    user_id = get_id_from_username(username_value)
    logger.info(f"Starting signup process for user: {username_value}", extra={"user_id": user_id})

    # === Initialisation popup conditions générales ===
    dialog_terms = ui.dialog()
    with dialog_terms, ui.card().classes("p-6 w-120"):
        ui.label(t("general_condition", lang_cookie)).classes("text-lg font-bold mb-4")
        ui.markdown(t("terms_text", lang_cookie)).style("white-space: pre-line;").classes("text-sm text-gray-700 mb-4")
        accept_checkbox = ui.checkbox(t("accept_condition", lang_cookie)).classes("mb-4")

        with ui.row().classes("justify-end gap-3"):
            ui.button(t("cancel", lang_cookie), on_click=dialog_terms.close)
            btn_accept_terms = ui.button(t("validate", lang_cookie)).props("disabled")

            def toggle_accept(e):
                if e.value:  # checkbox cochée → activer le bouton
                    btn_accept_terms.props(remove='disabled')
                else:        # checkbox décochée → désactiver le bouton
                    btn_accept_terms.props('disabled')

            accept_checkbox.on_value_change(toggle_accept)

    # === Confirmation par email ===
    if EMAIL_CONFIRMATION_SIGN_UP_ENABLED:
        dialog_confirm = ui.dialog()
        with dialog_confirm, ui.card().classes("p-6 w-80"):
            ui.label(t("enter_confirmation_code", lang_cookie)).classes("text-lg font-bold mb-4")
            ui.label(t("code_sent_by_mail", lang_cookie))
            code_input = ui.input(t("confirmation_code", lang_cookie)).classes("w-full mb-4")

            with ui.row().classes("justify-end gap-3"):
                ui.button(t("cancel", lang_cookie), on_click=dialog_confirm.close)
                ui.button(t("validate", lang_cookie), on_click=lambda e: verify_code(code_input, username_value, dialog_confirm, dialog_terms, btn_accept_terms, lang_cookie, mode=mode))
                ui.button(t('resend_code', lang_cookie), on_click=lambda e: resend_code(request, username_value, email_value, lang_cookie))

        dialog_confirm.open()

        if not send_code(email_value, username_value, lang_cookie):
            dialog_confirm.close()

    # === Confirmation quand vérification par email disabled ===
    else:  
        user_id = get_id_from_username(username_value)

        btn_accept_terms.on_click(lambda e: confirm_user_and_redirect_login(dialog_terms, user_id, lang_cookie, mode))
        dialog_terms.open()


# ------------------------
# Page function
# ------------------------
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

        # ------------------------
        # Login
        # ------------------------

        # === Champs à remplir ===
        ui.label(t("login", lang_cookie)).classes('text-2xl font-bold text-black mb-4')
        username = ui.input(t("username", lang_cookie)).classes('w-full mb-2').props('id=username-input')
        password = ui.input(t("password", lang_cookie), password=True, password_toggle_button=True).classes('w-full mb-4').props('id=password-input')
        login_warning = ui.label(t("password_caps", lang_cookie)).classes('text-red-600 text-sm mb-3 hidden')

        # === Bouton de login ===
        def handle_login():

            """Redirige vers une route qui gère le login"""

            username_value = username.value

            # Cas utilisateur existant
            try:
                user_id = get_id_from_username(username_value)
                user_info = get_user_info(user_id)

                # Cas site en maintenance (seulement admin peut se connecter)
                if get_setting("maintenance_mode") == "1" and not user_info.get('is_admin', False):
                    ui.notify(t("site_in_maintenance", lang_cookie), color='negative')
                    logger.info(f"Site in maintenance mode - login attempt blocked for username: {username.value}")
                    return

                if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):
                    confirmation_process(username_value, user_info['email'], request, lang_cookie, mode=0)
                else:
                    logger.info(f"Redirected to login route for user: {username_value}")
                    call_login_api(lang_cookie, mode=0)

            # Cas utilisateur inconnu
            except:

                # Cas site en maintenance
                if get_setting("maintenance_mode") == "1":
                    ui.notify(t("site_in_maintenance", lang_cookie), color='negative')
                    logger.info(f"Site in maintenance mode - login attempt blocked for username: {username.value}")
                    return

                logger.info(f"Redirected to login route for user: {username_value}")
                call_login_api(lang_cookie, mode=0)


        ui.button(t("connect", lang_cookie), on_click=handle_login) \
            .classes('btn-auth w-full mb-2').props('id=login-btn')
        
        # === Clique du bouton connection avec Enter ===
        ui.run_javascript("""
            document.addEventListener('keydown', function(event) {
                if (event.key === 'Enter') {
                    const active = document.activeElement;
                    if (active && (active.id === 'username-input' || active.id === 'password-input')) {
                        document.getElementById('login-btn')?.click();
                    }
                }
            });
            """)

        # ------------------------
        # Signup
        # ------------------------

         # === Champs à remplir ===
        ui.separator()
        ui.label(t("no_account", lang_cookie)).classes('text-lg font-bold text-black mt-2 mb-2')
        email = ui.input(t("email", lang_cookie)).classes('w-full mb-2').props('id=signup-email required')
        signup_user = ui.input(t("username", lang_cookie)).classes('w-full mb-2').props('id=signup-username required')
        signup_pass = ui.input(t("password", lang_cookie), password=True, password_toggle_button=True).classes('w-full mb-4').props('id=signup-password required')
        signup_warning = ui.label(t("password_caps", lang_cookie)).classes('text-red-600 text-sm mb-3 hidden')

        # === Warning quand majuscule sur la saisie du mot de passe ===
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

            if get_setting("allow_user_registration") == "0":
                ui.notify(t("registration_disabled", lang_cookie), color='negative')
                logger.info(f"User registration disabled - signup attempt blocked for username: {username_value}, email: {email_value}")
                return

            # Cas champ manquant
            if not username_value or not email_value or not password_value:
                ui.notify(t("mandatory_fields", lang_cookie), color='negative')
                logger.info(f"Missing fields for signup")
                return
            
            # Cas input trop longue
            if len(username_value) > 30 or len(email_value) > 50 or len(password_value) > 50:
                ui.notify(t("too_long", lang_cookie), color='negative')
                logger.info(f"Inputs too long: username: {len(username_value)}, email: {len(email_value)}, password: {len(password_value)}")
                return
            
            # Cas mot de passe ne respecte pas les conditions
            if ENABLE_MIN_PASSWORD_LENGHT: 
                min_lenght_password = get_setting("password_policy_min_length", 8)
                if len(password_value) < min_lenght_password:
                    ui.notify(f"{t('password_lenght', lang_cookie)}{min_lenght_password}{t('password_lenght_2', lang_cookie)}", color='negative')
                    logger.info(f"Password doesn't verify condition: len: {len(password_value)} vs min len: {min_lenght_password}")
                    return

            # Cas signup ok -> déclenche le mail de confirmation et la validation des conditions
            res_add_user = add_user(username_value, password_value, email_value)

            # Cas username ou email déjà existant
            if not res_add_user[0] and not res_add_user[1]:
                ui.notify(t("user_&_email_exists", lang_cookie), color='negative')
                logger.info(f"Username and email already exist: username: {username_value}, email: {email_value}")

            elif not res_add_user[0]:
                ui.notify(t("user_exists", lang_cookie), color='negative')
                logger.info(f"Username already exist: username: {username_value}")

            elif not res_add_user[1]:
                ui.notify(t("email_exists", lang_cookie), color='negative')
                logger.info(f"Email already exist: email: {email_value}")

            # Cas user OK -> lancement du process de signup
            else:
                confirmation_process(username_value, email_value, request, lang_cookie, mode=1)

        ui.button(t("signup", lang_cookie), on_click=handle_signup).classes('btn-auth w-full').props('id=signup-btn')

        # === Clique du bouton signup avec Enter ===
        ui.run_javascript("""
            document.addEventListener('keydown', function(event) {
                if (event.key === 'Enter') {
                    const active = document.activeElement;
                    if (active && (
                        active.id === 'signup-email' ||
                        active.id === 'signup-username' ||
                        active.id === 'signup-password'
                    )) {
                        document.getElementById('signup-btn')?.click();
                    }
                }
            });
            """)



@app.post("/api/login")
async def api_login(u: str = Form(...), p: str = Form(...), lang_cookie: str = Form(...), request: Request = None):

    """API pour effectuer le login"""
    
    client_id = request.client.host or u
    now = time.time()
    login_attempts[client_id] = [ts for ts in login_attempts[client_id] if now - ts < 60]
    if len(login_attempts[client_id]) >= 3:
        return JSONResponse({"status": "error", "notify": t("too_many_attempts", lang_cookie)})

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, password FROM users WHERE username = ?", (u,))
        row = cursor.fetchone()

    if not row or not verify_password(p, row[1]):
        login_attempts[client_id].append(now)
        logger.warning(f"Failed login attempt for username: {u}, ip: {request.client.host}")
        return JSONResponse({"status": "error", "notify": t("bad_credentials", lang_cookie)})

    user_id = row[0]
    user_info = get_user_info(user_id)

    if user_info.get('is_confirmed', False) or user_info.get('is_admin', False):

        if user_info.get('is_delivery_person', False) and not user_info.get('is_admin', False):
            role_redirect = "/delivery/home"
        else:
            role_redirect = "/home"

        response = RedirectResponse(role_redirect)
        generate_token(user_id, response=response)

        return response   

    else:
        return JSONResponse({"status": "not_confirmed"})


@ui.page('/logout')
def logout_page(request: Request = None):
    
    return logout(request)