from nicegui import ui, app
from fastapi.responses import RedirectResponse
from fastapi import Request

from components.navbar import navbar
from components.footer import footer_bar
from components.theme import apply_background
from services.auth import get_current_user
from services.users import record_visit, get_user_info
from services.logging_setup import get_logger
from translations.translations import t


@ui.page('/terms')
def terms(request: Request, open_section: str=False):

    """Affiche les conditions générales, les mentions légales et les conditions de confidentialité."""

    # === Setup initial ===

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for page terms: no valid token, ip: {host}")
        return RedirectResponse('/')
    
    logger = get_logger('nav')

    user_info = get_user_info(user_id)
    if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):  # utilisateur non confirmé et non admin
        logger.info("Access denied for page terms: not confirmed", extra={"user_id": user_id})
        return RedirectResponse('/')

    record_visit(user_id, '/terms')  # Page incluse dans l'historique de navigation

    apply_background()
    navbar(request)
    footer_bar(request)

    lang_cookie = request.cookies.get("language", "fr")

    # === Contenu de la page ===

    # Bouton retour
    with ui.row().classes('w-full p-4 sticky top-0 left-0 z-50 bg-transparent justify-start'):
        ui.button('⬅', on_click=lambda: ui.run_javascript('window.history.back()')) \
            .props('unelevated') \
            .classes('btn-back shadow-lg')
        
    
    with ui.card().classes('w-full max-w-3xl m-auto p-6 glass-card fade-in mt-6'):

        # === Section 1 : Condition générale d'utilisation ===
        with ui.expansion(icon='description', text=t("general_condition_title", lang_cookie), value=(open_section == "terms"))  \
            .classes('w-full bg-white/90 rounded-xl shadow-md mt-4 text-lg')  \
            .props('id="exp-terms"'):

            ui.markdown(t("terms_text", lang_cookie)).style("white-space: pre-line;").classes("text-sm text-gray-700 mb-4")

        
        # === Section 2 : Mentions légales ===
        with ui.expansion(icon='info', text=t("legal_mentions_title", lang_cookie), value=(open_section == "legale"))  \
            .classes('w-full bg-white/90 rounded-xl shadow-md mt-4 text-lg')  \
            .props('id="exp-legale"'):

            ui.markdown(t("legal_mentions_text", lang_cookie)).style("white-space: pre-line;").classes("text-sm text-gray-700 mb-4")
        

        # === Section 3 : Confidentialité ===
        with ui.expansion(icon='shield', text=t("privacy_title", lang_cookie), value=(open_section == "privacy"))  \
            .classes('w-full bg-white/90 rounded-xl shadow-md mt-4 text-lg')  \
            .props('id="exp-privacy"'):

            ui.markdown(t("privacy_text", lang_cookie)).style("white-space: pre-line;").classes("text-sm text-gray-700 mb-4")

        
    # === Zoom sur la section à ouvrir ===
    if open_section:
        ui.run_javascript(f"""
            const el = document.getElementById("exp-{open_section}");
            if (el) {{
                setTimeout(() => {{
                    el.scrollIntoView({{behavior:'smooth', block:'center'}});
                }}, 300);
            }}
        """)



   


