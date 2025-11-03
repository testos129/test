from nicegui import ui, app
from fastapi.responses import RedirectResponse
from fastapi import Request
import requests
from urllib.parse import unquote
import json

from components.navbar import navbar
from components.theme import apply_background
from services.auth import get_current_user, sessions
from services.users import record_visit, get_panier, get_wallet_balance, add_wallet_balance, delete_panier, register_order, get_user_info
from services.items import get_product, get_total_price_for_product, remove_stock_product, get_total_qty, get_pharmacy, get_total_price_for_product
from recommendations.user_product_matrix import update_with_panier
from services.distance import optimize_route
from translations.translations import t

            
@ui.page('/order')
def order(request: Request):

    """Page de validation de la commande avec calcul du coût de livraison et itinéraire optimisé"""

    # === Setup initial ===
    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    if not get_current_user():
        return RedirectResponse('/')

    token = app.storage.browser.get('token')
    user_id = sessions[token]

    user_info = get_user_info(user_id)
    if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):  # utilisateur non confirmé et non admin
        return RedirectResponse('/')

    record_visit(user_id, '/order')  # Page incluse dans l'historique de navigation

    apply_background()
    navbar(request)

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


        # === Calcul du montant total ===
        ui.state.total_global = 0

        for product_id, qty in panier_items.items():
            product = get_product(product_id)
            if not product:
                continue  # produit inexistant

            # Calcul du prix total via les pharmacies (prix min disponible)
            pricing = get_total_price_for_product(product_id, qty)

            ui.state.total_global += pricing["total_price"]

        ui.state.total_cost_text = t("delivery_fees_computing", lang_cookie)
        ui.state.delivery_cost_text = ""

        with ui.row().classes('items-center gap-2 mt-4'):
            total_cost_label = ui.label().bind_text(ui.state, 'total_cost_text').classes('text-lg font-bold mt-4 text-center')
            delivery_label = ui.label().bind_text(ui.state, 'delivery_cost_text').classes('text-sm text-gray-600')\
                .style('display: inline-block; transform: translateY(7px);')


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

        if address and not lat and not lng:
            try:
                geo_resp = requests.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": unquote(address), "format": "json", "limit": 1},
                    headers={"User-Agent": "AppPrototype"}
                )
                geo_data = geo_resp.json()
                if geo_data:
                    lat, lng = float(geo_data[0]['lat']), float(geo_data[0]['lon'])
            except Exception as e:
                ui.label(f"Erreur de géocodage : {e}").classes('text-red-500')
                return

        if not lat or not lng:
            ui.label(t("missing_coords", lang_cookie)).classes('text-red-500')
            return

        lat, lng = float(lat), float(lng)
        

        # === Confirmation de la commande ===
        def confirm_order():

            """Vérifie que la commande peut être effectuée et si oui, ajuste le wallet, vide le panier et ajuste les stocks"""

            # === Vérification des stocks ===
            for product_id, qty in panier_items.items():
                total_dispo = get_total_qty(product_id)  # quantité totale disponible en stock
                if qty > total_dispo:
                    ui.notify(f"{t('insufficient_stock', lang_cookie)}{get_product(product_id)['name']} {t('dispo', lang_cookie)}{total_dispo}{t('requested', lang_cookie)}{qty})", color='negative')
                    return
                
            def process_order():

                """Exécute le processus complet de validation de commande."""
                
                # === Enregistrement de la commande ===
                if address:
                    register_order(user_id, ui.state.delivery_cost, lat, lng, address)
                else:
                    register_order(user_id, ui.state.delivery_cost, lat, lng)
                update_with_panier(user_id)

                # === Débiter le wallet ===
                add_wallet_balance(user_id, ui.state.total_global_with_fee, request, is_expense=True)
                ui.notify(t("order_confirmed", lang_cookie), color='positive')

                # === Vider le panier ===
                delete_panier(user_id)

                # === Mettre à jour les stocks ===
                for product_id, qty in panier_items.items():
                    product = get_product(product_id)
                    if not product:  # cas produit inexistant
                        continue
                    remove_stock_product(product_id, qty)

                # === Redirection ===
                ui.navigate.to('/thanks')
            
            def handle_recharge_and_confirm(amount, popup):

                """Recharge le wallet et relance la commande."""

                popup.close()
                add_wallet_balance(user_id, amount, request, is_expense=False)
                ui.notify(t("wallet_recharged_2", lang_cookie), color="green")
                process_order()
         
            # === Vérification du solde de l'utilisateur ===
            wallet_balance = get_wallet_balance(user_id)
            total_cost = ui.state.total_global_with_fee

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
            ui.button(t("confirm_order", lang_cookie), on_click=confirm_order) \
                .props('unelevated') \
                .style('background-color:#2e7d32; color:white; font-weight:600; border-radius:6px; padding:8px 16px;') \
                .classes('btn-primary')

            ui.button(t("cancel_2", lang_cookie), on_click=lambda: ui.navigate.to('/panier')) \
                .props('unelevated') \
                .style('background-color:#c62828; color:white; font-weight:600; border-radius:6px; padding:8px 16px;') \
                .classes('btn-cancel')


    # === Grille principale : colonne gauche (panier) + colonne droite (itinéraire) ===
    with ui.grid().classes('w-full mt-4 grid-cols-1 lg:grid-cols-12 gap-6 items-stretch content-stretch'):

        # === Colonne gauche : produits du panier ===
        with ui.column().classes('w-full lg:col-span-4 gap-4'):
            # Tableau des produits
            for product_id, qty in panier_items.items():
                product = get_product(product_id)
                if not product:
                    continue

                # Calcule/actualise le prix pour ce produit
                pricing = get_total_price_for_product(product_id, qty)

                # Card produits
                with ui.card().classes('w-full shadow-md rounded-xl p-5'):
                    with ui.row().classes('w-full items-center justify-between gap-4'):
                        ui.image(product['image']).style(
                            'width:96px; height:96px; object-fit:cover; border-radius:12px;'
                        )
                        with ui.column().classes('flex-1'):
                            ui.label(product['name']).classes('font-bold text-lg')
                            if pricing["details"]:
                                ui.label(
                                    f"{t('average_price', lang_cookie)}{pricing['total_price']/qty:.2f} €"
                                ).classes('text-gray-600 text-sm')
                            ui.label(f"{t('quantity', lang_cookie)}{qty}").classes('text-gray-600 text-sm')
                        ui.label(f"{pricing['total_price']:.2f} €").classes('font-semibold text-lg')


        # === Colonne droite : itinéraire ===
        with ui.column().classes('w-full lg:col-span-8'):

            # === Récupération des pharmacies de la commande ===
            pharmacy_ids = []
            panier = get_panier(user_id)
            if panier:
                for product_id, qty in panier.items():
                    details = get_total_price_for_product(product_id, qty)['details']
                    pharmacy_ids += [pharmacy['pharmacy_id'] for pharmacy in details]

            pharmacy_ids = set(pharmacy_ids)
            pharmacies = [
                {
                    "name": get_pharmacy(pid)["name"],
                    "lat": get_pharmacy(pid)["coords"]["lat"],
                    "lng": get_pharmacy(pid)["coords"]["lng"]
                }
                for pid in pharmacy_ids
            ]

            if not pharmacies:
                ui.label(t("no_pharmacies_order", lang_cookie)).classes('text-red-500')
                return

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
                    var waypoints = [L.latLng({lat}, {lng})];
                    pharmacies.forEach(function(ph) {{
                        waypoints.push(L.latLng(ph.lat, ph.lng));
                    }});

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

                        // --- Envoi au backend (NiceGUI / FastAPI)
                        fetch('/set_distance', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{ distance: totalDistance }})
                        }})
                        .then(r => r.json())
                        .then(data => {{
                            console.log("Distance envoyée avec succès:", data);
                        }})
                        .catch(err => {{
                            console.error("Erreur lors de l'envoi de la distance:", err);
                        }})
                        .finally(() => {{
                            // Toujours masquer les overlays même si erreur réseau
                            if (overlay) overlay.style.display = 'none';
                            if (deliveryOverlay) deliveryOverlay.style.display = 'none';
                        }});
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
            
            
    ui.state.route_distance = 0  # valeur en mètres


    # === Mise à jour du coût dans l'interface ===
    @app.post("/set_distance")
    async def set_distance(request: Request):

        data = await request.json()
        distance_m = data.get("distance", 0)
        ui.state.route_distance = distance_m

        ui.state.delivery_cost = 3 + 0.001 * ui.state.route_distance
        ui.state.total_global_with_fee = ui.state.total_global + ui.state.delivery_cost

        ui.state.total_cost_text = f"{t('total_cost', lang_cookie)}{ui.state.total_global_with_fee:.2f} €"
        ui.state.delivery_cost_text = f"({t('delivery_fees', lang_cookie)}{ui.state.delivery_cost:.2f} €)"

        return {"status": "ok"}
