from nicegui import ui, app
from fastapi.responses import RedirectResponse
import asyncio
from fastapi import Request
import re

from services.auth import get_current_user
from services.users import get_wallet_balance, add_wallet_balance, get_wallet_history, get_user_info
from components.navbar import navbar
from components.footer import footer_bar
from components.theme import apply_background
from services.logging_setup import get_logger
from translations.translations import t


@ui.page('/wallet')
def wallet_page(request: Request):

    """Page de gestion du wallet utilisateur."""

    # === Setup initial ===

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for page wallet: no valid token, ip: {host}")
        return RedirectResponse('/')
    
    logger = get_logger('nav')

    user_info = get_user_info(user_id)
    if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):  # utilisateur non confirmé et non admin
        logger.info("Access denied for page wallet: not confirmed", extra={"user_id": user_id})
        return RedirectResponse('/')

    apply_background()
    navbar(request)
    footer_bar(request)

    lang_cookie = request.cookies.get("language", "fr")

    # Bouton retour
    with ui.row().classes('w-full p-4 sticky top-0 left-0 z-50 bg-transparent'):
        ui.button(t("return_home", lang_cookie), on_click=lambda: ui.navigate.to('/home')) \
            .props('unelevated') \
            .classes('btn-back shadow-lg')


    # === Contenu de la page ===
    
    with ui.column().classes('items-center w-full'):

        # === Titre ===
        ui.label(t("my_wallet", lang_cookie)).classes('text-2xl font-bold text-green-800 mb-4')

        # === Solde actuel ===
        balance_label = ui.label(f"{t('current_balance', lang_cookie)}{get_wallet_balance(user_id):.2f} €") \
                            .classes('text-xl font-bold mb-4')

        # === Rechargement du wallet ===
        ui.label(t("recharge_wallet", lang_cookie)).classes('text-lg font-semibold mt-8')

        async def recharge(amount: float):  # async pour afficher la notification avant le reload de l'ui

            add_wallet_balance(user_id, amount, request, is_expense=False)
            balance_label.set_text(f"{t('current_balance', lang_cookie)}{get_wallet_balance(user_id):.2f} €")
            logger.info(f"Wallet recharged of {amount}", extra={"user_id": user_id})
            ui.notify(f"{t('wallet_recharged', lang_cookie)}{amount:.2f} € 💳", color="positive")
            
            await asyncio.sleep(1)  # attend 1 seconde avant de reload
            ui.navigate.reload()  # Reload la page pour actualisé l'historique du wallet

        # === Bouton recharche rapide (montants prédéfinis) ===
        def change_recharge_amount(amount: float):
            montant_input.value = amount

        with ui.row().classes('gap-4 mt-2'):
            ui.button("15 €", on_click=lambda: change_recharge_amount(15.0)) \
                .classes('bg-green-400 text-white font-bold px-4 py-2 rounded-lg')
            ui.button("20 €", on_click=lambda: change_recharge_amount(20.0)) \
                .classes('bg-green-600 text-white font-bold px-4 py-2 rounded-lg')
            ui.button("50 €", on_click=lambda: change_recharge_amount(50.0)) \
                .classes('bg-green-800 text-white font-bold px-4 py-2 rounded-lg')

        # === Rechargement montant personnalisé ===
        with ui.row().classes('gap-2 mt-4'):
            montant_input = ui.number(label=f"{t('custom_amount', lang_cookie)}(€)", min=1, value=10) \
                            .classes('w-40')
            ui.button(t("recharge", lang_cookie), on_click=lambda: recharge(float(montant_input.value or 0))) \
                .classes('btn-success bg-amber-500 text-white font-bold px-4 py-2 rounded-lg')
            
        # === Historique ===
        ui.label(t("transactions_history", lang_cookie)).classes('text-lg font-semibold mt-6')
        history = get_wallet_history(user_id)

        # === Etat pour la pagination ===
        class WalletState:
            current_page = 0
            items_per_page = 20

        wallet_state = WalletState()

        wallet_container = ui.column().classes('w-full max-w-md gap-3 mt-2 items-center')
        wallet_pagination = ui.row().classes('justify-center items-center gap-4 mt-4')

        def update_wallet_history():

            """Met à jour l'affichage de l'historique avec une limite de 20 transactions par page."""

            wallet_container.clear()
            wallet_pagination.clear()

            if not history:
                with wallet_container:
                    ui.label(t("no_transaction", lang_cookie)).classes('text-gray-500')
                return

            # === Pagination ===
            total_pages = max(1, (len(history) + wallet_state.items_per_page - 1) // wallet_state.items_per_page)
            start = wallet_state.current_page * wallet_state.items_per_page
            end = start + wallet_state.items_per_page
            paginated_history = history[start:end]

            # === Affichage des transactions ===
            with wallet_container:
                for date, amount, desc in paginated_history:

                    if amount > 0:
                        border_color = 'border-green-500'
                        text_color = 'text-green-700'
                        icon_name = 'attach_money'
                    else:
                        border_color = 'border-red-500'
                        text_color = 'text-red-700'
                        icon_name = 'shopping_cart'

                    def format_desc(desc: str):

                            """
                            Sépare la description d'une commande contenant un numéro.
                            """

                            match = re.match(r"(.*#)(\d+)(.*)", desc)
                            if match:
                                return match.group(1).strip(), match.group(2) + match.group(3)
                            return desc, ""
                    
                    if "Crédit livraison" in desc:
                        text_desc = t(format_desc(desc)[0], lang_cookie) + t(format_desc(desc)[1], lang_cookie)
                    else:
                        text_desc = t(desc, lang_cookie)

                    with ui.card().classes(
                        f'w-full border border-gray-300 border-l-4 {border_color} bg-white shadow-md rounded-xl p-3 transition hover:shadow-lg hover:translate-y-[-2px]'
                    ):
                        with ui.row().classes('justify-between items-center w-full'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon(icon_name).classes(f'{text_color}')
                                ui.label(text_desc).classes(f'font-semibold {text_color}')
                            ui.label(f"{amount:+.2f} €").classes(f'font-bold {text_color}')
                        ui.label(date).classes('text-sm text-gray-500')

            # === Contrôles de pagination ===
            with wallet_pagination:
                if wallet_state.current_page > 0:
                    ui.button(icon='chevron_left', on_click=lambda: change_wallet_page(-1)) \
                        .props('flat').classes('rounded-full')
                ui.label(f"{t('page', lang_cookie)}{wallet_state.current_page + 1} / {total_pages}").classes('text-gray-600 mt-1')
                if wallet_state.current_page < total_pages - 1:
                    ui.button(icon='chevron_right', on_click=lambda: change_wallet_page(1)) \
                        .props('flat').classes('rounded-full')


        def change_wallet_page(delta: int):

            """Change la page actuelle de l'historique du wallet."""
            
            wallet_state.current_page += delta
            update_wallet_history()

        update_wallet_history()