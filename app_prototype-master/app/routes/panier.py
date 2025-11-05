from nicegui import ui, app
from fastapi.responses import RedirectResponse
from fastapi import Request

from app.components.navbar import navbar
from app.components.theme import apply_background
from app.services.auth import get_current_user, sessions
from app.services.users import record_visit, get_panier, add_panier_item, remove_panier_item, get_user_info, update_user
from app.services.items import get_product, get_total_price_for_product, get_total_qty
from app.translations.translations import t


@ui.page('/panier')
def panier(request: Request):

    """Affiche le panier de l'utilisateur avec les options de gestion et de commande."""

    # === Setup initial ===
    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    if not get_current_user():
        return RedirectResponse('/')

    token = app.storage.browser.get('token')
    user_id = sessions[token]

    user_info = get_user_info(user_id)
    if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):  # utilisateur non confirmé et non admin
        return RedirectResponse('/')

    record_visit(user_id, '/panier')  # Page incluse dans l'historique de navigation

    apply_background()
    navbar(request)

    lang_cookie = request.cookies.get("language", "fr")
    distance_cookie = float(request.cookies.get("max_distance", "10"))

    # Bouton retour
    with ui.row().classes('w-full p-4 sticky top-0 left-0 z-50 bg-transparent justify-start'):
        ui.button('⬅', on_click=lambda: ui.run_javascript('window.history.back()')) \
            .props('unelevated') \
            .classes('btn-back shadow-lg')

    show_block = {"visible": False}


    # === Bloc de saisie de l'itinéraire ===
    @ui.refreshable
    def itinerary_block():

        if show_block["visible"]:
            with ui.card().classes(
                'bg-white p-4 shadow-lg rounded-xl w-72'
            ):
                ui.label(t("delivery_addr", lang_cookie)).classes('text-lg font-semibold mb-3 text-center')

                # === Option 1 : Géolocalisation ===
                def use_current_location():

                    pos_not_found_msg = t("pos_not_found", lang_cookie)
                    geo_not_supported_msg = t("geo_not_supported", lang_cookie)

                    ui.run_javascript(f"""
                        if (navigator.geolocation) {{
                            navigator.geolocation.getCurrentPosition(
                                function(pos) {{
                                    const lat = pos.coords.latitude;
                                    const lng = pos.coords.longitude;
                                    window.location.href = '/order?lat=' + lat + '&lng=' + lng;
                                }},
                                function(err) {{
                                    alert("{pos_not_found_msg}: " + err.message);
                                }}
                            );
                        }} else {{
                            alert("{geo_not_supported_msg}");
                        }}
                    """)

                ui.button(t("use_pos", lang_cookie), on_click=use_current_location)\
                    .classes('btn-secondary w-full mb-3')

                ui.separator().classes('my-2')

                # === Option 2 : saisie manuelle de l'adresse ===
                manual_input = ui.input(
                    label=t("enter_addr", lang_cookie), value=user_info['delivery_address']
                ).props('outlined clearable').classes('w-full mb-2')

                def validate_addr(address):

                    """"""

                    if not user_info['delivery_address']:  # Pas encore d'adresse définie
                        update_user(user_id, None, None, address)
                    ui.navigate.to(f"/order?address={manual_input.value}")


                ui.button(t("validate_addr", lang_cookie), on_click=lambda: validate_addr(manual_input.value)
                    ).classes('btn-success w-full')


    def toggle_block():
        show_block["visible"] = not show_block["visible"]
        itinerary_block.refresh()


    # === Conteneur global du panier ===
    with ui.column().classes('items-center w-full'):
        ui.label(t("panier", lang_cookie)).classes('text-2xl font-bold text-center mt-4')

        with ui.row().classes('items-center justify-center gap-4 mb-4') as order_row:
            total_label = ui.label().classes('text-lg font-semibold')
            ui.button(t("order", lang_cookie), on_click=toggle_block) \
                .props('unelevated') \
                .style('background-color:#388e3c; color:white; font-weight:600; border-radius:6px; padding:6px 12px;') \
                .classes('btn-success')

            itinerary_block()

        panier_container = ui.column().classes('w-full items-center')
        with ui.column().classes('items-center justify-center gap-4 mb-4') as empty_panier:
            ui.label(t("empty_panier", lang_cookie)).classes('text-gray-500 text-center mt-4')
            ui.button(t("find_products", lang_cookie), on_click=lambda: ui.navigate.to('/home')) \
                .props('unelevated').classes('btn-recommended')
        empty_panier.visible = False


    # === Fonctions de gestion du panier ===
    def refresh_panier():

        """Rafraîchit l'affichage du panier utilisateur dans l'interface."""

        # === Récupération du panier ===
        panier_container.clear()
        panier_count = get_panier(user_id)

        if not panier_count:
            empty_panier.visible = True
            total_label.text = ""
            order_row.visible = False
            return
        else:
            empty_panier.visible = False
            order_row.visible = True

        # === Calcul du montant total ===
        total = sum(get_total_price_for_product(pid, qty)['total_price'] for pid, qty in panier_count.items())
        total_label.text = f"{t('total_panier', lang_cookie)}{total:.2f} €"

        # === Affichage produits ===
        for pid, qty in panier_count.items():
            prod = get_product(pid)
            if not prod:
                continue

            with panier_container:
                with ui.card().style(
                    'width: min(100%, 520px); margin: 10px auto; padding: 10px; box-sizing: border-box;'
                ):
                    with ui.row().classes('items-center').style('width:100%; gap:16px;'):

                        # === Image du produit ===
                        ui.image(prod['image']).style(
                            'width:80px; height:80px; border-radius:10px; object-fit:cover; flex-shrink:0;'
                        )

                        # === Nom et prix ===
                        with ui.column().classes('flex-1'):
                            ui.label(prod['name']).classes('text-lg font-bold')
                            ui.label(get_total_price_for_product(pid, qty)).classes('text-gray-600')

                        # === Boutons + / - ===
                        with ui.row().classes('items-center').style('gap:4px;'):

                            if qty >= 2:
                                ui.button('-', on_click=lambda _, pid=pid: on_remove_one(pid)) \
                                    .props('round unelevated') \
                                    .style('background-color:#d32f2f; color:white; width:32px; height:32px;')
                            ui.label(str(qty)).classes('text-lg font-bold')

                            if qty <= get_total_qty(pid):  # S'assurer qu'il y a encore du stock
                                ui.button('+', on_click=lambda _, pid=pid: on_add_one(pid)) \
                                    .props('round unelevated') \
                                    .style('background-color:#388e3c; color:white; width:32px; height:32px;')

                        # === Bouton suppression d'un produit ===
                        ui.button('', icon='delete', on_click=lambda _, pid=pid: on_delete_all(pid)) \
                            .props('round unelevated') \
                            .style('background-color:#b71c1c; color:white; width:40px; height:40px;')

    def on_add_one(pid):

        add_panier_item(user_id, pid, request, allow_duplicates=True)
        refresh_panier()

    def on_remove_one(pid):

        remove_panier_item(user_id, pid, request, remove_all=False)
        refresh_panier()

    def on_delete_all(pid):
        
        remove_panier_item(user_id, pid, request, remove_all=True)
        refresh_panier()

    refresh_panier()