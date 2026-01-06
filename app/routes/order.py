from nicegui import ui, app
from fastapi.responses import RedirectResponse
from fastapi import Request
import json
import httpx

from components.navbar import navbar
from components.theme import apply_background
from components.footer import footer_bar
from services.auth import get_current_user
from services.users import record_visit, get_panier, get_wallet_balance, add_wallet_balance, delete_panier, register_order, get_user_info, update_user
from services.items import get_product, get_total_price_for_product, remove_stock_product, get_total_qty, get_pharmacy, get_closest_pharmacy
from recommendations.user_product_matrix import update_with_panier
from services.distance import optimize_route
from services.address import get_coords_from_address
from services.logging_setup import get_logger
from translations.translations import t

from services.file_io import load_yaml
functionalities_switch = load_yaml('components/functionalities_switch.yaml')
ENABLE_MAX_DISTANCE_PHARMACY = functionalities_switch.get('ENABLE_MAX_DISTANCE_PHARMACY', True)
ENABLE_USE_STOCK_MODE = functionalities_switch.get('ENABLE_USE_STOCK_MODE', True)


@ui.page('/order')
async def order(request: Request):

    """Page de validation de la commande avec calcul du coût de livraison et itinéraire optimisé"""

    # === Setup initial ===

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for page order: no valid token, ip: {host}")
        return RedirectResponse('/')
    
    logger = get_logger('nav')

    user_info = get_user_info(user_id)
    if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):  # utilisateur non confirmé et non admin
        logger.info("Access denied for page order: not confirmed", extra={"user_id": user_id})
        return RedirectResponse('/')

    record_visit(user_id, '/order')  # Page incluse dans l'historique de navigation

    apply_background()
    navbar(request)
    footer_bar(request)

    lang_cookie = request.cookies.get("language", "fr")
    distance_cookie = float(request.cookies.get("max_distance", "10"))

    panier_items = get_panier(user_id)

    # === Contenu de la page ===

    with ui.column().classes('items-center w-full max-w-3xl mx-auto p-4 gap-4'):

        # === Titre et description ===
        ui.label(t("validate_order", lang_cookie)).classes('text-3xl font-bold text-center mt-4')
        ui.label(t("verify_panier_content", lang_cookie)) \
            .classes('text-gray-700 text-center')

        if not panier_items:
            ui.label(t("empty_panier", lang_cookie)).classes('text-lg text-gray-500 mt-6')
            return

        user_store = app.storage.user
        user_store.setdefault('order_dict', {})
        order_dict = user_store['order_dict']
        order_dict['total_global'] = 0
        order_dict['total_cost_text'] = t("delivery_fees_computing", lang_cookie)
        order_dict['delivery_cost_text'] = ""
        order_dict['route_distance_text'] = ""

        with ui.row().classes('items-center gap-2 mt-4'):
            total_cost_label = ui.label().bind_text_from(order_dict, 'total_cost_text').classes('text-lg font-bold mt-4 text-center')
            delivery_label = ui.label().bind_text_from(order_dict, 'delivery_cost_text').classes('text-sm text-gray-600')\
                .style('display: inline-block; transform: translateY(7px);')
            
        if not ENABLE_USE_STOCK_MODE:
            ui.label(t("price_estimation", lang_cookie)).classes('text-lg text-orange-600')
        
        warning_label = ui.label().bind_text(order_dict, 'route_distance_text').classes('text-lg text-orange-600')

        warning_missing_products_label = ui.label("").classes('text-lg text-orange-600')

        # === Overlay de chargement en attendant le calcul du coût de la livraison ===
        delivery_fees_computing_message = t("delivery_fees_computing", lang_cookie)

        overlay = ui.html(f"""
            <div id="delivery-overlay" style="
                position: absolute;
                top: 0; left: 0;
                width: 100%; height: 100%;
                background: rgba(255,255,255,0.9);
                display: flex;
                justify-content: center;
                align-items: center;
                font-size: 1.2em;
                font-weight: bold;
                z-index: 9999;
            ">
                <div class="spinner"></div>
                {delivery_fees_computing_message}
            </div>
        """)

        # === Récupération des coordonnées de l'utilisateur ===
        params = request.query_params
        lat = params.get('lat')
        lng = params.get('lng')
        address = params.get('address')
        address_type = params.get('type')

        if address and not lat and not lng:

            result_address = get_coords_from_address(address)
            if result_address[0]:
                lat, lng = result_address[1]
            else:
                if result_address[1] == "no_addr_found":
                    overlay.visible = False
                    ui.label(t("no_addr_found", lang_cookie)).classes('text-red-500 text-lg italic')
                    return
                else:
                    overlay.visible = False
                    ui.label(f"{t('error_geocoding', lang_cookie)}{result_address[2]}").classes('text-red-500')
                    return
        
        if not lat or not lng:
            overlay.visible = False
            ui.label(t("missing_coords", lang_cookie)).classes('text-red-500')
            return

        lat, lng = float(lat), float(lng)

        if not address_type:  # Position utilisateur utilisée
            address_details = ui.input(t("address_details", lang_cookie)).classes('w-full mt-2')

        elif address_type == "1":  # Adresse principale utilisée
            address_details = ui.input(t("address_details", lang_cookie), value=user_info['main_address_details']).classes('w-full mt-2')

        elif address_type == "2":  # Adresse secondaire utilisée
            address_details = ui.input(t("address_details", lang_cookie), value=user_info['secondary_address_details']).classes('w-full mt-2')

        elif address_type == "3":  # Adresse entrée manuellement
            address_details = ui.input(t("address_details", lang_cookie)).classes('w-full mt-2')

            def register_details():

                if not user_info['main_address_details']:
                    update_user(user_id, 
                                main_address_details=address_details.value)
            register_details()
                
        else:
            address_details = ui.input(t("address_details", lang_cookie)).classes('w-full mt-2')
        

        # === Confirmation de la commande ===
        def confirm_order():

            """Vérifie que la commande peut être effectuée et si oui, ajuste le wallet, vide le panier et ajuste les stocks"""

            # === Vérification des stocks (que en mode stock) ===
            if ENABLE_USE_STOCK_MODE:
                for product_id, qty in panier_items.items():
                    total_dispo = get_total_qty(product_id)  # quantité totale disponible en stock
                    if qty > total_dispo:
                        logger.warning(f"Insufficient stock for product {product_id}, missing quantity: {qty - total_dispo}", extra={"user_id": user_id})
                        ui.notify(f"{t('insufficient_stock', lang_cookie)}{get_product(product_id)['name']} {t('dispo', lang_cookie)}{total_dispo}{t('requested', lang_cookie)}{qty})", color='negative')
                        return
                
            def process_order():

                """Exécute le processus complet de validation de commande."""
                
                # === Enregistrement de la commande ===
                if address:
                    if ENABLE_USE_STOCK_MODE:
                        register_order(user_id, order_dict['delivery_cost'], lat, lng, address, address_details.value)
                    else:
                        register_order(user_id, order_dict['delivery_cost'], lat, lng, address, address_details.value, closest_pharmacy['pharmacy']['id'])
                else:
                    if ENABLE_USE_STOCK_MODE:
                        register_order(user_id, order_dict['delivery_cost'], lat, lng, address_details.value)
                    else:
                        register_order(user_id, order_dict['delivery_cost'], lat, lng, address_details.value, closest_pharmacy['pharmacy']['id'])
                
                logger.info("Order registered", extra={"user_id": user_id})
                update_with_panier(user_id)

                # === Débiter le wallet ===
                add_wallet_balance(user_id, order_dict['total_global_with_fee'], request, is_expense=True)
                logger.info(f"User debited of {order_dict['total_global_with_fee']}", extra={"user_id": user_id})
                ui.notify(t("order_confirmed", lang_cookie), color='positive')

                # === Vider le panier ===
                delete_panier(user_id)

                # === Mettre à jour les stocks (uniquement en mode stock) ===
                if ENABLE_USE_STOCK_MODE:
                    for product_id, qty in panier_items.items():
                        product = get_product(product_id)
                        if not product:  # cas produit inexistant
                            continue
                        remove_stock_product(product_id, qty)
                    logger.info("Stock updated following order", extra={"user_id": user_id})


                # === Redirection ===
                ui.navigate.to('/thanks')
            
            def handle_recharge_and_confirm(amount, popup):

                """Recharge le wallet et relance la commande."""

                popup.close()
                add_wallet_balance(user_id, amount, request, is_expense=False)
                logger.info(f"Wallet recharged of {amount}", extra={"user_id": user_id})
                ui.notify(t("wallet_recharged_2", lang_cookie), color="green")
                process_order()
        
            # === Vérification du solde de l'utilisateur ===
            wallet_balance = get_wallet_balance(user_id)
            total_cost = order_dict['total_global_with_fee']

            if wallet_balance < total_cost:
                # Montant manquant
                missing_amount = round(total_cost - wallet_balance, 2)

                # Création du popup
                with ui.dialog() as recharge_popup, ui.card():
                    ui.label(t("insufficient_balance", lang_cookie)).classes("text-lg font-semibold mb-2")
                    ui.label(f"{t('missing_amount', lang_cookie)} : {missing_amount:.2f} €").classes("text-gray-700 font-semibold mb-3")
                    with ui.row().classes("justify-end gap-3"):
                        ui.button(t("cancel", lang_cookie), on_click=recharge_popup.close).props("flat")
                        ui.button(f"{t('recharge_now', lang_cookie)} : {missing_amount:.2f} €",
                                on_click=lambda: handle_recharge_and_confirm(missing_amount, recharge_popup)) \
                            .props("unelevated color='green'")

                recharge_popup.open()
                return

            # === Si solde suffisant, on traite normalement ===
            process_order()


        # === Boutons Confirmer/Annuler ===
        with ui.row().classes('justify-center gap-4 mt-6'):
            confirm_button = ui.button(t("confirm_order", lang_cookie), on_click=confirm_order) \
                                .props('unelevated') \
                                .style('background-color:#2e7d32; color:white; font-weight:600; border-radius:6px; padding:8px 16px;') \
                                .classes('btn-primary')

            ui.button(t("cancel_2", lang_cookie), on_click=lambda: ui.navigate.to('/panier')) \
                .props('unelevated id=cancel-btn') \
                .style('background-color:#c62828; color:white; font-weight:600; border-radius:6px; padding:8px 16px;') \
                .classes('btn-cancel')
            
            # Run du bouton Annuler avec Escape
            ui.run_javascript("""
                document.addEventListener('keydown', function(event) {
                    if (event.key === 'Escape') {
                        const cancelBtn = document.getElementById('cancel-btn');
                        if (cancelBtn) cancelBtn.click();
                    }
                });
                """)
                    

        with ui.row().classes('items-center justify-center'):
            no_pharmacie_warning = ui.label().classes('text-red-500 text-center text-2xl font-bold')

    # === Grille principale : colonne gauche (panier) + colonne droite (itinéraire) ===
    with ui.grid().classes('w-full mt-4 grid-cols-1 lg:grid-cols-12 gap-6 items-stretch content-stretch'):

        # === Colonne gauche : produits du panier ===
        with ui.column().classes('w-full lg:col-span-4 gap-4'):
            # Tableau des produits
            pharmacy_ids = []
            total_remaining = 0

            if panier_items:
                for product_id, qty in panier_items.items():
                    product = get_product(product_id)
                    if not product:
                        continue
                    
                    # Cas stock
                    if ENABLE_USE_STOCK_MODE:
                        # Calcule/actualise le prix pour ce produit
                        if ENABLE_MAX_DISTANCE_PHARMACY:
                            pricing = get_total_price_for_product(product_id, qty, lat, lng, distance_cookie)
                        else:
                            pricing = get_total_price_for_product(product_id, qty)

                        order_dict['total_global'] += pricing["total_price"]

                        pharmacy_ids += [pharmacy['pharmacy_id'] for pharmacy in pricing['details']]
                        if pricing['missing_qty']:
                            total_remaining += pricing['missing_qty']
                        
                        taken_qty = sum([detail['taken_qty'] for detail in pricing['details']])
                    
                    # Cas non stock
                    else:
                        if product['estimated_price']:
                            order_dict['total_global'] += product['estimated_price'] * qty
                        taken_qty = qty

                    if taken_qty > 0:
                        # Card produits
                        with ui.card().classes('w-full shadow-md rounded-xl p-5'):
                            with ui.row().classes('w-full items-center justify-between gap-4'):
                                ui.image(product['image']).style(
                                    'width:96px; height:96px; object-fit:cover; border-radius:12px;'
                                )
                                with ui.column().classes('flex-1'):
                                    # Nom du produit
                                    ui.label(product['name']).classes('font-bold text-lg')

                                    # Prix total produit
                                    if ENABLE_USE_STOCK_MODE:
                                        ui.label(f"{pricing['total_price']:.2f} €").classes('font-semibold text-lg')
                                    else:
                                        if product['estimated_price']:
                                            ui.label(f"~ {(product['estimated_price'] * taken_qty):.2f} €").classes('font-semibold text-lg')
                                        else:
                                            ui.label(t("no_estimation", lang_cookie)).classes('font-semibold')

                                # Prix moyen et quantité produit
                                if ENABLE_USE_STOCK_MODE:
                                    if pricing["details"]:
                                        ui.label(
                                            f"{t('average_price', lang_cookie)}{(pricing['total_price']/taken_qty):.2f} €"
                                        ).classes('text-gray-600 text-sm')
                                    ui.label(f"{t('quantity', lang_cookie)}{taken_qty}").classes('text-gray-600 text-sm')
                                                                
                                else:
                                    if product['estimated_price']:
                                        ui.label(
                                            f"{t('average_price', lang_cookie)}~ {product['estimated_price']:.2f} €"
                                        ).classes('text-gray-600 text-sm')
                                    ui.label(f"{t('quantity', lang_cookie)}{taken_qty}").classes('text-gray-600 text-sm')
                                    
        if total_remaining > 0:
            warning_missing_products_label.text = f"{t('products_not_found_1', lang_cookie)}({total_remaining}){t('products_not_found_2', lang_cookie)}"


        # === Colonne droite : itinéraire ===
        with ui.column().classes('w-full lg:col-span-8'):

            # === Récupération des pharmacies de la commande ===

            # Quand pas en mode stock, on récupère juste la pharmacie la plus proche de l'adresse de livraison
            if not ENABLE_USE_STOCK_MODE:
                if ENABLE_MAX_DISTANCE_PHARMACY:
                    closest_pharmacy = get_closest_pharmacy(lat, lng, distance_cookie)  # None si aucune pharmacie à la distance souhaitée
                else:
                    closest_pharmacy = get_closest_pharmacy(lat, lng)
                
                if closest_pharmacy['success']:
                    pharmacy_ids = [closest_pharmacy['pharmacy']['id']]
            
            pharmacy_ids = set(pharmacy_ids)

            # Cas aucune pharmacie trouvée
            if not pharmacy_ids:
                overlay.visible = False
                confirm_button.props("disabled")
                no_pharmacie_warning.text = t("no_pharmacies_order", lang_cookie)

                return
            
            pharmacies = [
                {
                    "name": get_pharmacy(pid)["name"],
                    "lat": get_pharmacy(pid)["coords"]["lat"],
                    "lng": get_pharmacy(pid)["coords"]["lng"]
                }
                for pid in pharmacy_ids
            ] 

            # === Réordonner l'ordre de visite pour minimiser la distance ===
            pharmacies_ordered = optimize_route(lat, lng, pharmacies)

            # === Affichage de la carte interactive ===
            with ui.element('div').props('id=map-container').classes('w-full').style(
                'position: relative; height: 600px; border-radius: 12px;'
            ):
                ui.element('div').props('id=map').style('width: 100%; height: 100%; border-radius: 12px;')

                computing_itinerary_message = t("computing_itinerary", lang_cookie)

                ui.html(f"""
                    <div id="loading-overlay">
                        <div class="spinner"></div>
                        {computing_itinerary_message}
                    </div>
                """)

            ui.add_head_html("""
                <style>
                    #loading-overlay {
                        position: absolute;
                        top: 0; left: 0;
                        width: 100%; height: 100%;
                        background: rgba(255,255,255,0.9);
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 1.2em;
                        font-weight: bold;
                        z-index: 9999;
                    }
                    .spinner {
                        border: 6px solid #f3f3f3;
                        border-top: 6px solid #3498db;
                        border-radius: 50%;
                        width: 40px;
                        height: 40px;
                        animation: spin 1s linear infinite;
                        margin-right: 12px;
                    }
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                    .leaflet-tile {
                        background-color: #f0f0f0; /* évite les carrés gris */
                    }
                </style>
            """)

            ui.add_head_html("""
                <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
                <link rel="stylesheet" href="https://unpkg.com/leaflet-routing-machine@3.2.12/dist/leaflet-routing-machine.css" />
                <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
                <script src="https://unpkg.com/leaflet-routing-machine@3.2.12/dist/leaflet-routing-machine.js"></script>
            """)

            intinerary_message = t("itinerary", lang_cookie)
            close_itinerary_message = t("close_itinerary", lang_cookie)
            user_position_message = t("user_pos", lang_cookie)

            ui.run_javascript(f"""
                setTimeout(function() {{

                    // --- Création de la carte
                    var map = L.map('map').setView([{lat}, {lng}], 13);

                    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                        maxZoom: 19,
                        detectRetina: true,
                        crossOrigin: true
                    }}).addTo(map);

                    // --- Marqueurs pharmacies
                    var pharmacies = {json.dumps(pharmacies_ordered)};
                    pharmacies.forEach(function(ph) {{
                        L.marker([ph.lat, ph.lng]).addTo(map).bindPopup("💊 " + ph.name);
                    }});

                    // --- Marqueur départ
                    L.marker([{lat}, {lng}]).addTo(map).bindPopup("{user_position_message}");

                    // --- Waypoints pour le routage
                    // var waypoints = [L.latLng({lat}, {lng})];
                    // pharmacies.forEach(function(ph) {{
                    //    waypoints.push(L.latLng(ph.lat, ph.lng));
                    // }});
                    var waypoints = [];
                    pharmacies.forEach(function(ph) {{
                        waypoints.push(L.latLng(ph.lat, ph.lng));
                    }});
                    waypoints.push(L.latLng({lat}, {lng})); // utilisateur = point d'arrivée

                    // --- Overlay livraison (visible pendant le calcul)
                    var deliveryOverlay = document.getElementById("delivery-overlay");
                    if (deliveryOverlay) {{
                        deliveryOverlay.style.display = 'flex';
                    }}

                    // --- Contrôle de routage avec OSRM public
                    var routingControl = L.Routing.control({{
                        waypoints: waypoints,
                        router: L.Routing.osrmv1({{
                            serviceUrl: 'https://router.project-osrm.org/route/v1'
                        }}),
                        routeWhileDragging: false,
                        addWaypoints: false,
                        createMarker: function() {{ return null; }},
                        show: true,
                        collapsible: true
                    }}).on('routesfound', function(e) {{
                        // Masquer overlays dès que le trajet est trouvé
                        var overlay = document.getElementById("loading-overlay");
                        if (overlay) overlay.style.display = 'none';
                        if (deliveryOverlay) deliveryOverlay.style.display = 'none';

                        // --- Calcul distance totale
                        var totalDistance = e.routes[0].summary.totalDistance; // mètres
                        console.log("Itinéraire trouvé. Distance totale:", totalDistance, "m");

                        if (overlay) overlay.style.display = 'none';
                        if (deliveryOverlay) deliveryOverlay.style.display = 'none';
                    }}).addTo(map);

                    // --- Masquer complètement le panneau de routage
                    var panel = routingControl.getContainer ? routingControl.getContainer() : routingControl._container;
                    if (panel) {{
                        var collapseBtn = panel.querySelector('.leaflet-routing-collapse-btn');
                        if (collapseBtn) collapseBtn.style.display = 'none';
                        panel.style.display = 'none';
                    }}

                    // --- Bouton custom pour afficher / cacher l'itinéraire
                    var isPanelVisible = false;
                    var ToggleCtrl = L.Control.extend({{
                        options: {{ position: 'topright' }},
                        onAdd: function (map) {{
                            var btn = L.DomUtil.create('button', 'leaflet-bar');
                            btn.innerHTML = "{intinerary_message}";
                            Object.assign(btn.style, {{
                                background: 'white',
                                border: '1px solid #ccc',
                                padding: '4px 8px',
                                cursor: 'pointer',
                                font: 'inherit'
                            }});
                            L.DomEvent.on(btn, 'click', function(e) {{
                                L.DomEvent.stopPropagation(e);
                                L.DomEvent.preventDefault(e);
                                if (!panel) return;

                                isPanelVisible = !isPanelVisible;
                                panel.style.display = isPanelVisible ? 'block' : 'none';
                                btn.innerHTML = isPanelVisible ? "{close_itinerary_message}" : "{intinerary_message}";
                            }});
                            return btn;
                        }}
                    }});
                    map.addControl(new ToggleCtrl());

                }}, 500);
                """)
            
            
            OSRM_URL = "https://router.project-osrm.org/route/v1/driving"

            async def compute_total_distance(waypoints):

                """waypoints = liste de tuples (lat, lng)
                Exemple : [(lat1, lng1), (lat2, lng2), ..., (latN, lngN)]
                
                Retourne : distance totale en mètres (float)"""

                if len(waypoints) < 2:
                    return 0.0

                # OSRM attend lng,lat (et non lat,lng)
                coord_string = ";".join([f"{lng},{lat}" for lat, lng in waypoints])

                url = f"{OSRM_URL}/{coord_string}?overview=false"

                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.get(url)

                    try:
                        data = response.json()
                        
                    except json.JSONDecodeError:
                        logger.warning(f"OSRM is not available", extra={"user_id": user_id})
                        raise ValueError(t("osrm_not_available", lang_cookie))

                if "routes" not in data:
                    logger.warning(f"OSRM didn't find a route", extra={"user_id": user_id})
                    raise ValueError(t("osrm_no_route", lang_cookie))

                return data["routes"][0]["distance"]  # distance en mètres
            

            async def update_distance_and_cost():

                """Stocke les informations de distance et coût de livraison dans le user_store"""

                full_waypoints = [(ph["lat"], ph["lng"]) for ph in pharmacies_ordered] + [(lat, lng)]
                distance_m = await compute_total_distance(full_waypoints)


                if distance_m < 0 or distance_m > 10_000_000:
                    logger.warning(f"Anormal distance: {distance_m}", extra={"user_id": user_id})

                distance_m = max(0, min(distance_m, 10_000_000))  # Pour éviter des valeurs aberrantes

                order_dict = user_store.setdefault('order_dict', {})
                        
                order_dict['distance'] = distance_m

                order_dict['delivery_cost'] = 3 + 0.001 * distance_m
                order_dict['total_global_with_fee'] = order_dict['total_global'] + order_dict['delivery_cost']

                distance_threshold = 5000  # en mètres
                if distance_m > distance_threshold:
                    order_dict['route_distance_text'] = t("warning_distance", lang_cookie)
                else:
                    order_dict['route_distance_text'] = ""

                if ENABLE_USE_STOCK_MODE:
                    order_dict['total_cost_text'] = f"{t('total_cost', lang_cookie)}~ {order_dict['total_global_with_fee']:.2f} €"
                else:
                    order_dict['total_cost_text'] = f"{t('total_cost', lang_cookie)}{order_dict['total_global_with_fee']:.2f} €"
                order_dict['delivery_cost_text'] = f"({t('delivery_fees', lang_cookie)}{order_dict['delivery_cost']:.2f} €)"

                # print(order_dict)

                
            await update_distance_and_cost()