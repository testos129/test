from nicegui import ui, app

app.add_static_files('/static', 'static')


def apply_background():

    """Injecte les styles globaux pour les différentes pages."""

    # CSS externe
    ui.add_head_html('<link rel="stylesheet" href="/static/styles.css">')
    
    # JS externe
    ui.add_head_html('<script src="/static/script.js"></script>')