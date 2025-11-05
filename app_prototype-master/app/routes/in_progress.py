from nicegui import ui, app
from fastapi.responses import RedirectResponse
from fastapi import Request
import json

from app.components.navbar import navbar
from app.components.theme import apply_background
from app.services.auth import get_current_user, sessions
from app.services.users import record_visit, get_user_info, get_orders_for_customer, get_order_details
from app.services.items import get_pharmacy
from app.services.distance import optimize_route
from app.translations.translations import t

            
@ui.page('/orders_in_progress')
def orders_in_progress(request: Request):

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

    # === Contenu de la page ===
    # Retour à l'accueil
    with ui.row().classes("w-full justify-between items-center"):
        ui.button(t("return_home", lang_cookie), on_click=lambda: ui.navigate.to("/home")).classes("btn-back")

    pending_orders = get_orders_for_customer(user_id, status='pending')
    in_progress_orders = get_orders_for_customer(user_id)

    if not in_progress_orders and not pending_orders:
        with ui.row().classes("justify-center w-full mt-4"):
            ui.label(t("no_in_progress_orders", lang_cookie)).classes("text-lg text-center")
    else:
        with ui.row().classes("justify-center w-full mt-4"):
            ui.label(t("my_in_progress_orders", lang_cookie)).classes("text-2xl font-bold text-center")

        # Initialisation si elle n'existe pas encore
        if not hasattr(ui.state, "current_order"):
            ui.state.current_order = None

        # Fonction pour mettre à jour
        def update_current_order(order_id):
            ui.state.current_order = order_id
            ui.navigate.reload()  # recharge l'UI avec la nouvelle valeur

        
        with ui.row().classes('w-full lg:grid lg:grid-cols-12 gap-6 mt-6'):

            # === Colonne gauche : card commande ===
            with ui.column().classes("w-full lg:col-span-4 gap-4 h-[calc(100vh-8rem)] overflow-y-auto pr-2"):
                for order in in_progress_orders:
                    with ui.card().classes("w-full mt-4 bg-green-100 text-green-800 cursor-pointer") \
                            .on('click', lambda e, oid=order['order_id']: update_current_order(oid)):
                        ui.label(f"{t('commande_num', lang_cookie)}{order['order_id']}").classes("font-bold")
                        ui.label(f"{t('delivery_person_name', lang_cookie)}{order['delivery_person']}")
                        ui.label(f"{t('delivery_address', lang_cookie)}{order['address']}")
                        ui.label(f"{t('delivery_cost', lang_cookie)}{order['delivery_cost']:.2f}€").classes("mt-4")
                        ui.label(f"{t('total_cost', lang_cookie)}{order['total']:.2f}€").classes("font-bold mt-2")

                for order in pending_orders:
                    with ui.card().classes("w-full mt-4 bg-yellow-100 text-yellow-800 cursor-pointer") \
                            .on('click', lambda e, oid=order['order_id']: update_current_order(oid)):
                        ui.label(f"{t('commande_num', lang_cookie)}{order['order_id']}").classes("font-bold")
                        ui.label(t("pending_order", lang_cookie))
                        ui.label(f"{t('delivery_address', lang_cookie)}{order['address']}")
                        ui.label(f"{t('delivery_cost', lang_cookie)}{order['delivery_cost']:.2f}€").classes("mt-4")
                        ui.label(f"{t('total_cost', lang_cookie)}{order['total']:.2f}€").classes("font-bold mt-2")


            # === Colonne droite : itinéraire ===
            with ui.column().classes('w-full lg:col-span-8 flex items-center justify-center'): #.classes('w-full lg:col-span-8 sticky top-4 h-[calc(100vh-2rem)] overflow-hidden'):
                if ui.state.current_order:

                    order_details = get_order_details(ui.state.current_order)

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
                        ui.label(t("no_pharmacies_order", lang_cookie)).classes('text-red-500')
                        return

                    # === Réordonner l'ordre de visite pour minimiser la distance ===
                    if order_details['status'] == "pending":
                        # ui.label(t("order_not_taken_yet", lang_cookie)).classes("font-bold mt-2")
                        ui.label(t("order_not_taken_yet", lang_cookie)).classes("font-bold text-2xl text-center mt-4")
                    else:

                        # TO CHANGE
                        user_lat = order_details['lat']
                        user_lng = order_details['lng']

                        pharmacies_ordered = optimize_route(user_lat, user_lng, pharmacies, order_details['lat'], order_details['lng'])

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
                                var map = L.map('map').setView([{user_lat}, {user_lng}], 13);

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
                                L.marker([{user_lat}, {user_lng}]).addTo(map).bindPopup("{user_position_message}");

                                // --- Waypoints pour le routage
                                var waypoints = [L.latLng({user_lat}, {user_lng})];
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
                                    fetch('/set_distance_order', {{
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
                @app.post("/set_distance_order")
                async def set_distance_order(request: Request):

                    data = await request.json()
                    distance_m = data.get("distance", 0)
                    ui.state.route_distance = distance_m

                    return {"status": "ok"}