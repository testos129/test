from nicegui import ui
from datetime import datetime
from fastapi import Request

from translations.translations import t

def footer_bar(request: Request):

    """Défini le footer appliqué sur les différentes pages du site"""

    lang_cookie = request.cookies.get("language", "fr")

    year = datetime.now().year

    with ui.footer().classes(
        'static w-full bg-gray-100 text-gray-700 py-4 px-4 border-t flex flex-col md:flex-row '
        'justify-between items-center text-sm'
    ):  # static rend le footer non sticky
        
        ui.label(f"© {year} PharmaLink — {t('all_rights', lang_cookie)}").classes('opacity-70')

        with ui.row().classes('gap-4 mt-2 md:mt-0'):
            ui.link('CGU', '/terms?open_section=terms').classes('text-black no-underline hover:text-gray-500')
            ui.link('Mentions légales', '/terms?open_section=legale').classes('text-black no-underline hover:text-gray-500')
            ui.link('Confidentialité', '/terms?open_section=privacy').classes('text-black no-underline hover:text-gray-500')
            ui.link('Contact', '/profile?open_contact=true').classes('text-black no-underline hover:text-gray-500')