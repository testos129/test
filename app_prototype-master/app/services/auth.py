from nicegui import ui, app
from fastapi.responses import RedirectResponse
from typing import Optional
from fastapi import Request

sessions = {}  # token -> username

# def get_current_user(request: Optional[Request] = None) -> Optional[int]:

#     """Récupère l'ID de l'utilisateur actuel à partir du cookie de session."""

#     if not request:
#         return None

#     token = request.cookies.get("session_token")
#     if not token:
#         return None

#     return sessions.get(token)

def get_current_user() -> Optional[int]:

    """Récupère l'id de l'utilisateur actuel en fonction du cookie de session."""

    token = app.storage.browser.get('token')  # Récupère le token stocker côté navigateur

    return sessions.get(token)


def logout():

    """Déconnecte l'utilisateur et redirige vers la page de connexion."""

    token = app.storage.browser.get('token')
    if token in sessions:
        del sessions[token]
    app.storage.browser['token'] = None

    return RedirectResponse('/')  # Retour à la page racine de l'app