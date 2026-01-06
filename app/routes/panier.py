from nicegui import ui, app
from fastapi.responses import RedirectResponse
from fastapi import Request

from components.navbar import navbar
from components.footer import footer_bar
from components.theme import apply_background
from services.auth import get_current_user
from services.users import record_visit, get_panier, add_panier_item, remove_panier_item, get_user_info, update_user
from services.items import get_product, get_total_price_for_product, get_total_qty
from services.logging_setup import get_logger
from translations.translations import t

from services.file_io import load_yaml
functionalities_switch = load_yaml('components/functionalities_switch.yaml')
ENABLE_USE_STOCK_MODE = functionalities_switch.get('ENABLE_USE_STOCK_MODE', True)


@ui.page('/panier')
def panier(request: Request):

    """Affiche le panier de l'utilisateur avec les options de gestion et de commande."""

    # === Setup initial ===

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for page panier: no valid token, ip: {host}")
        return RedirectResponse('/')
    
    logger = get_logger('nav')

    user_info = get_user_info(user_id)
    if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):  # utilisateur non confirmé et non admin
        logger.info("Access denied for page itinerary: not confirmed", extra={"user_id": user_id})
        return RedirectResponse('/')

    record_visit(user_id, '/panier')  # Page incluse dans l'historique de navigation

    apply_background()
    navbar(request)
    footer_bar(request)

    lang_cookie = request.cookies.get("language", "fr")

    # Bouton retour
    with ui.row().classes('w-full p-4 sticky top-0 left-0 z-50 bg-transparent justify-start'):
        ui.button(t("return_home", lang_cookie), on_click=lambda: ui.navigate.to('/home')) \
            .props('unelevated') \
            .classes('btn-back shadow-lg')


    with ui.column().classes('items-center w-full'):

        # === TITRE PANIER ===
        ui.label(t("panier", lang_cookie)).classes('text-3xl font-bold text-center mt-4')

        # === TOTAL + WARNING ===
        with ui.column().classes('items-center mt-2 mb-6'):
            total_label = ui.label().classes('text-xl font-semibold')

            if not ENABLE_USE_STOCK_MODE:
                show_warning = ui.label(t("price_estimation", lang_cookie)).classes('text-lg text-orange-600 font-medium text-center')

        
        with ui.column().classes("items-center justify-center gap-4 mt-4") as empty_panier:
                ui.label(t("empty_panier", lang_cookie)).classes(
                    "text-gray-500 text-center"
                )
                ui.button(
                    t("find_products", lang_cookie),
                    on_click=lambda: ui.navigate.to('/home')
                ).props("unelevated").classes("btn-recommended")

        empty_panier.visible = False


    with ui.column().classes("w-full items-center gap-6 mt-6") as show_content:

        # === CARD PANIER ===
        with ui.card().classes("w-full max-w-2xl bg-white p-4 shadow-lg rounded-xl"):

            with ui.row().classes("w-full justify-center"):
                ui.label(t("panier_2", lang_cookie)).classes("text-lg font-semibold mb-4 text-center")
            panier_container = ui.column().classes("w-full items-center")

        # === CARD ADRESSE ===
        with ui.card().classes(
            "w-full max-w-2xl bg-white p-4 shadow-lg rounded-xl"
        ):
            with ui.row().classes("w-full justify-center"):
                ui.label(t("delivery_addr", lang_cookie)).classes("text-lg font-semibold mb-8 text-center")   

            # === Option 1 : Géolocalisation ===
            def use_current_location():

                """Récupère la geolicalisation de l'utilisateur depuis le navigateur"""

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

            with ui.row().classes("w-full justify-center"):
                ui.button(t("use_pos", lang_cookie), on_click=use_current_location)\
                    .classes('btn-success mb-3')
                
                # === Option 2 : adresse déjà définie ===
                if user_info['main_address_street'] and user_info['main_address_city'] and user_info['main_address_postal_code']:
                    search_address_1 = user_info['main_address_street'] + ", " + user_info['main_address_postal_code'] + ", " + user_info['main_address_city']
                    ui.button(f"{search_address_1}", on_click=lambda: ui.navigate.to(f"/order?address={search_address_1}&type=1")) \
                    .classes('btn-success mb-3')

                if user_info['secondary_address_street'] and user_info['secondary_address_city'] and user_info['secondary_address_postal_code']:
                    search_address_2 = user_info['secondary_address_street'] + ", " + user_info['secondary_address_postal_code'] + ", " + user_info['secondary_address_city'] 
                    ui.button(f"{search_address_2}", on_click=lambda: ui.navigate.to(f"/order?address={search_address_2}&type=2")) \
                    .classes('btn-success mb-3')

                # === Option 3 : saisie manuelle de l'adresse ===
                with ui.expansion(text=t("manual_input_addr", lang_cookie), value=False).classes('w-full bg-white rounded-xl shadow-md mt-4'):
                    address_input = ui.input(t("street_number", lang_cookie)).classes('w-full mt-2').props('id=manual-address outlined clearable')
                    with ui.row():
                        city_input = ui.input(t("city", lang_cookie)).classes('w-full mt-2').props('id=manual-city outlined clearable')
                        postal_code_input = ui.input(t("postal_code", lang_cookie)).classes('w-full mt-2').props('id=manual-postal-code outlined clearable')

                    def validate_addr():

                        """Save the user address if there's not already one and navigate to the itinerary page"""

                        if not address_input.value or not city_input.value or not postal_code_input.value:
                            ui.notify(t("mandatory_addr_fields", lang_cookie), color="negative")
                            return

                        if not user_info['main_address_street']:  # Pas encore d'adresse principale définie
                            update_user(user_id, 
                                        main_address_street=address_input.value, 
                                        main_address_city=city_input.value, 
                                        main_address_postal_code=postal_code_input.value)
                            logger.info("Main address updated after an itinerary search", extra={"user_id": user_id})
                        
                        logger.info("Panier confirmed", extra={"user_id": user_id})
                        search_address = address_input.value + ", " + postal_code_input.value + ", " + city_input.value
                        ui.navigate.to(f"/order?address={search_address}&type=3")

                    ui.button(t("validate_addr", lang_cookie), on_click=lambda: validate_addr()) \
                        .classes('btn-success w-full').props('id=validate-addr-btn')
                
                # Activation du bouton avec Enter
                ui.run_javascript("""
                    document.addEventListener('keydown', function(event) {
                        if (event.key === 'Enter') {
                            const active = document.activeElement;
                            if (active && (
                                active.id === 'manual-address' ||
                                active.id === 'manual-city' ||
                                active.id === 'manual-postal-code'
                            )) {
                                document.getElementById('validate-addr-btn')?.click();
                            }
                        }
                    });
                    """)


    # === Fonctions de gestion du panier ===
    def refresh_panier():

        """Rafraîchit l'affichage du panier utilisateur dans l'interface."""

        # === Récupération du panier ===
        panier_container.clear()
        panier_count = get_panier(user_id)

        if not panier_count:
            empty_panier.visible = True
            total_label.text = ""
            show_content.visible = False
            show_warning.visible = False
            return
        else:
            empty_panier.visible = False
            show_content.visible = True
            show_warning.visible = True

        # === Calcul du montant total ===
        if ENABLE_USE_STOCK_MODE:
            total = sum(get_total_price_for_product(pid, qty)['total_price'] for pid, qty in panier_count.items())
            total_label.text = f"{t('total_panier', lang_cookie)}{total:.2f} €"
        else:
            total = 0
            for pid, qty in panier_count.items():
                estimated_price = get_product(pid)['estimated_price']
                if estimated_price:
                    total += estimated_price * qty
            total_label.text = f"{t('total_panier', lang_cookie)} ~ {total:.2f} €"

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
                            
                            if ENABLE_USE_STOCK_MODE:
                                ui.label(f"{get_total_price_for_product(pid, qty)['total_price']:.2f}€").classes('text-gray-600')
                            else:
                                estimated_price = get_product(pid)['estimated_price']
                                if estimated_price:
                                    ui.label(f"~ {(estimated_price * qty):.2f}€").classes('text-gray-600')
                                else:
                                    ui.label(t("no_estimation", lang_cookie)).classes('text-gray-600')


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