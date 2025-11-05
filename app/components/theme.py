from pathlib import Path
from nicegui import ui, app

STATIC_DIR = Path(__file__).resolve().parent.parent / 'static'
app.add_static_files('/static', str(STATIC_DIR))


def apply_background():

    """Injecte les styles globaux pour les différentes pages."""

    # CSS externe
    ui.add_head_html('<link rel="stylesheet" href="/static/styles.css">')
    
    # JS externe
    ui.add_head_html('<script src="/static/script.js"></script>')