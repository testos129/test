from nicegui import ui, app
from fastapi.responses import RedirectResponse
from typing import Optional
from fastapi import Request
import hashlib
import time
import threading

sessions = {}  # token -> (user_id, expiration_date)
session_lock = threading.Lock()


def get_current_user(request: Optional[Request] = None) -> Optional[int]:

    """Récupère l'ID de l'utilisateur actuel à partir du cookie de session."""

    if not request:
        return None
    
    token_from_cookie = request.cookies.get("token")
    if not token_from_cookie:
        return None
    
    hashed = hashlib.sha256(token_from_cookie.encode()).hexdigest()
    with session_lock:
        info = sessions.get(hashed)

    if info:
        user_id, exp = info
        if time.time() < exp:
            return user_id
        else:
            with session_lock:
               sessions.pop(hashed, None)  # token expiré

    return None


def logout(request: Optional[Request] = None):

    """Déconnecte l'utilisateur et redirige vers la page de connexion."""

    if not request:
        return None
    
    token_from_cookie = request.cookies.get("token")
    if not token_from_cookie:
        return RedirectResponse('/')
    
    hashed = hashlib.sha256(token_from_cookie.encode()).hexdigest()
    with session_lock:
        sessions.pop(hashed, None)

    return RedirectResponse('/')