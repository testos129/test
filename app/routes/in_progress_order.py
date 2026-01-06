from nicegui import ui, app
from fastapi.responses import RedirectResponse
from fastapi import Request
import json

from components.navbar import navbar
from components.footer import footer_bar
from components.theme import apply_background
from services.auth import get_current_user
from services.users import record_visit, get_user_info, get_orders_for_customer, get_order_details, get_user_from_id, get_delivery_person_list_for_customer
from services.items import get_pharmacy
from services.distance import optimize_route
from services.logging_setup import get_logger
from translations.translations import t

            
@ui.page('/orders_in_progress/{order_id}')
def order_details(order_id: str, request: Request):

    """Page de validation de la commande avec calcul du coût de livraison et itinéraire optimisé"""

    # === Setup initial ===
    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for page in progress: no valid token, ip: {host}")
        return RedirectResponse('/')

    logger = get_logger('nav')

    user_info = get_user_info(user_id)
    if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):  # utilisateur non confirmé et non admin
        logger.info("Access denied for page in progress: not confirmed", extra={"user_id": user_id})
        return RedirectResponse('/')

    record_visit(user_id, '/order')  # Page incluse dans l'historique de navigation

    apply_background()
    navbar(request)
    footer_bar(request)

    lang_cookie = request.cookies.get("language", "fr")

    # === Contenu de la page ===

    # Retour à la page précendente
    with ui.row().classes("w-full justify-between items-center"):
        ui.button(t("return", lang_cookie), on_click=lambda: ui.navigate.to("/orders_in_progress")).classes("btn-back")

    pending_orders = get_orders_for_customer(user_id, status='pending')
    in_progress_orders = get_orders_for_customer(user_id)

    if not in_progress_orders and not pending_orders:
        with ui.row().classes("justify-center w-full mt-4"):
            ui.label(t("no_in_progress_orders", lang_cookie)).classes("text-lg text-center")
    else:
        with ui.row().classes("justify-center w-full mt-4"):
            ui.label(f"{t('order_number', lang_cookie)}{order_id}").classes("font-bold text-2xl text-center")

        with ui.row().classes('w-full lg:grid lg:grid-cols-12 gap-6 mt-6'):

            # === Colonne gauche : card commande ===
            def display_order(order, with_details=False):

                """Display information about an order"""

                ui.label(f"{t('commande_num', lang_cookie)}{order['order_id']}").classes("font-bold")
                if 'delivery_person' in order.keys():
                    delivery_person = order['delivery_person']
                else:
                    delivery_person = get_user_from_id(order['delivery_person_id'])

                ui.label(f"{t('delivery_person_name', lang_cookie)}{delivery_person}")
                ui.label(f"{t('delivery_address', lang_cookie)}{order['address']}")

                if with_details:
                    if order.get('address_details'):
                        ui.label(f"{t('additional_details', lang_cookie)}{order['address_details']}")
                    if order.get('order_code'):
                        ui.label(f"{t('order_code', lang_cookie)}{order['order_code']}").classes("mt-2")
                    ui.label(f"{t('delivery_cost', lang_cookie)}{order['delivery_cost']:.2f}€").classes("mt-4")
                    ui.label(f"{t('total_cost', lang_cookie)}{order['total']:.2f}€").classes("font-bold mt-2")


            with ui.column().classes("w-full lg:col-span-4 gap-4 h-[calc(100vh-8rem)] overflow-y-auto items-center pr-2"):
                
                current_order = get_order_details(order_id)
                with ui.card().classes("w-full mt-4"):
                    display_order(current_order, with_details=True)

                # with ui.row().classes("items-center"):
                ui.label(t("other_orders", lang_cookie)).classes("text-center font-semibold")

                with ui.column().classes("w-full overflow-y-auto pr-2"):

                    no_other_orders = True

                    for order in in_progress_orders:
                        other_order_id = order['order_id']
                        if str(other_order_id) != str(order_id):
                            no_other_orders = False
                            with ui.card().classes("w-full mt-4 bg-green-100 text-green-800 cursor-pointer")  \
                                .on('click', lambda e, oid=other_order_id: ui.navigate.to(f'/orders_in_progress/{oid}')):
                                display_order(order, with_details=False)

                    for order in pending_orders:
                        other_order_id = order['order_id']
                        if str(other_order_id) != str(order_id):
                            no_other_orders = False
                            with ui.card().classes("w-full mt-4 bg-yellow-100 text-yellow-800 cursor-pointer")  \
                                .on('click', lambda e, oid=other_order_id: ui.navigate.to(f'/orders_in_progress/{oid}')):
                                display_order(order, with_details=False)

                    if no_other_orders:
                        ui.label(t("no_other_orders", lang_cookie)).classes("text-center text-gray-600 mt-4")

            # === Colonne droite : itinéraire ===

            with ui.column().classes('w-full lg:col-span-8 flex items-center justify-center'):

                order_details = get_order_details(order_id)

                # === Récupération des pharmacies de la commande ===
                items = order_details['items']
                pharmacy_ids = []
                for item in items:
                    pharmacy_ids.append(item['pharmacy_id'])
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
                    ui.label(t("no_pharmacies_order", lang_cookie)).classes('text-red-500 text-2xl font-bold mt-4')
                    return

                # === Réordonner l'ordre de visite pour minimiser la distance ===
                if order_details['status'] == "pending":
                    ui.label(t("order_not_taken_yet", lang_cookie)).classes("font-bold text-2xl text-center mt-4")
                else:

                    # Récupérer la position du livreur
                    delivery_person_id = order_details['delivery_person_id']
                    if delivery_person_id:
                        delivery_person_info = get_user_info(delivery_person_id)
                        delivery_lat, delivery_lng = delivery_person_info['current_lat'], delivery_person_info['current_lng']

                        if not delivery_lat or not delivery_lng:
                            ui.label(t("no_delivery_coords", lang_cookie)).classes('text-red-500 text-2xl font-bold mt-4')
                            return
                    else:
                        ui.label(t("no_delivery_person", lang_cookie)).classes('text-red-500 text-2xl font-bold mt-4')
                        return
                        

                    pharmacies_ordered = optimize_route(delivery_lat, 
                                                        delivery_lng, 
                                                        pharmacies, 
                                                        order_details['lat'], 
                                                        order_details['lng'], 
                                                        t("delivery_destination", lang_cookie))

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
                    delivery_position_message = t("delivery_position", lang_cookie)

                    ui.run_javascript(f"""
                        setTimeout(function() {{

                            // --- Création de la carte
                            var map = L.map('map').setView([{delivery_lat}, {delivery_lng}], 13);

                            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                                maxZoom: 19,
                                detectRetina: true,
                                crossOrigin: true
                            }}).addTo(map);

                            // --- Marqueurs pharmacies
                            var pharmacies = {json.dumps(pharmacies_ordered)};
                            pharmacies.forEach(function(ph) {{
                                L.marker([ph.lat, ph.lng]).addTo(map).bindPopup(ph.name);
                            }});

                            // --- Marqueur départ (rouge)
                            var userIcon = L.icon({{
                                iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
                                shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.3/images/marker-shadow.png',
                                iconSize: [25, 41],
                                iconAnchor: [12, 41],
                                popupAnchor: [1, -34],
                                shadowSize: [41, 41]
                            }});

                            var userMarker = L.marker([{delivery_lat}, {delivery_lng}], {{icon: userIcon}}).addTo(map);
                            userMarker.bindTooltip("{delivery_position_message}", {{
                                permanent: true,
                                direction: "top",
                                offset: [0, -10]
                            }}).openTooltip();

                            // --- Waypoints pour le routage
                            var waypoints = [L.latLng({delivery_lat}, {delivery_lng})];
                            pharmacies.forEach(function(ph) {{
                                waypoints.push(L.latLng(ph.lat, ph.lng));
                            }});
                            var pharmaciesWaypoints = waypoints.slice(1); // pour le refresh

                            // --- Overlay livraison (visible pendant le calcul)
                            var deliveryOverlay = document.getElementById("delivery-overlay");
                            if (deliveryOverlay) {{
                                deliveryOverlay.style.display = 'flex';
                            }}

                            // --- Contrôle de routage avec OSRM
                            var routingControl = L.Routing.control({{
                                waypoints: waypoints,
                                router: L.Routing.osrmv1({{ serviceUrl: 'https://router.project-osrm.org/route/v1' }}),
                                routeWhileDragging: false,
                                addWaypoints: false,
                                createMarker: function() {{ return null; }},
                                show: true,
                                collapsible: true
                            }}).on('routesfound', function(e) {{
                                var overlay = document.getElementById("loading-overlay");
                                if (overlay) overlay.style.display = 'none';
                                if (deliveryOverlay) deliveryOverlay.style.display = 'none';

                                // --- Calcul distance totale
                                var totalDistance = e.routes[0].summary.totalDistance;
                                console.log("Itinéraire trouvé. Distance:", totalDistance, "m");

                                if (overlay) overlay.style.display = 'none';
                                if (deliveryOverlay) deliveryOverlay.style.display = 'none';
                            }}).addTo(map);

                            // --- Masquer panneau
                            var panel = routingControl.getContainer ? routingControl.getContainer() : routingControl._container;
                            if (panel) {{
                                var collapseBtn = panel.querySelector('.leaflet-routing-collapse-btn');
                                if (collapseBtn) collapseBtn.style.display = 'none';
                                panel.style.display = 'none';
                            }}

                            // --- Bouton custom itinéraire
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

                            // --- Variables pour refresh API
                            var lastLat = {delivery_lat};
                            var lastLng = {delivery_lng};

                            // --- Rafraîchissement toutes les 10 secondes
                            function refreshRouteIfNeeded() {{

                                fetch('/api/get_delivery_position?user_id={delivery_person_id}')
                                    .then(r => r.json())
                                    .then(data => {{

                                        if (!data.lat || !data.lng) {{
                                            console.warn("Position livreur indisponible");
                                            return;
                                        }}

                                        var newLat = data.lat;
                                        var newLng = data.lng;

                                        if (newLat !== lastLat || newLng !== lastLng) {{

                                            lastLat = newLat;
                                            lastLng = newLng;

                                            // Mettre à jour le marqueur livreur
                                            userMarker.setLatLng([lastLat, lastLng]);

                                            // Recalculer l'itinéraire
                                            routingControl.setWaypoints(
                                                [L.latLng(lastLat, lastLng)].concat(pharmaciesWaypoints)
                                            );

                                            console.log("Itinéraire recalculé avec nouvelle position livreur:", lastLat, lastLng);
                                        }}
                                    }})
                                    .catch(err => console.error("Erreur API position livreur:", err));
                            }}

                            setInterval(refreshRouteIfNeeded, 10000);

                        }}, 500);
                    """)
                

@app.get("/api/get_delivery_position")
def get_delivery_position(user_id: int, request: Request):

    """ API pour récupérer la position actuelle du livreur """

    client_user_id = get_current_user(request)
    if not client_user_id:
        return {"error": "Unauthorized"}, 401
    
    # Vérifier que le client a le droit de voir la position du livreur
    if not user_id in get_delivery_person_list_for_customer(client_user_id):
        return {"error": "Forbidden"}, 403

    delivery_person_info = get_user_info(user_id)
    coords = delivery_person_info['current_lat'], delivery_person_info['current_lng']
    if not coords:
        return {"lat": None, "lng": None}
    
    # print({"lat": coords[0], "lng": coords[1]})

    return {"lat": coords[0], "lng": coords[1]}
                    