from nicegui import ui, app
from fastapi import Request
from fastapi.responses import RedirectResponse
import json

from components.theme import apply_background
from components.navbar_delivery import navbar_delivery
from services.auth import get_current_user, sessions
from services.users import get_user_info, get_order_details, take_order, get_orders_for_delivery_person
from services.items import get_pharmacy, get_product
from services.distance import optimize_route
from services.settings import get_setting
from translations.translations import t


@ui.page("/delivery/order/{order_id}")
def delivery_order_page(request: Request, order_id: int):

    """ Page de gestion d'une commande réservée."""

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    if not get_current_user():
        return RedirectResponse('/')

    token = app.storage.browser.get('token')
    user_id = sessions[token]

    user_info = get_user_info(user_id)
    if not user_info.get('is_admin', False):
        if not user_info.get('is_confirmed', False) or not user_info.get('is_delivery_person', False):  # utilisateur non confirmé ou non livreur
            return RedirectResponse('/')
    
    # Styles globaux + navbar + cookies
    apply_background()
    navbar_delivery(request)

    lang_cookie = request.cookies.get("language", "fr")

    # === Contenu de la page ===
    # === Récupération des coordonnées utilisateur depuis les paramètres d'URL ===
    params = request.query_params
    user_lat = float(params.get('lat'))
    user_lng = float(params.get('lng'))
    
    # Retour à l'accueil livreur et mes commandes
    with ui.row():
        ui.button(t("return_home", lang_cookie), on_click=lambda: ui.navigate.to("/delivery/home")).classes("btn-back")
        with ui.button(t("my_deliveries", lang_cookie), on_click=lambda: ui.navigate.to(f"/delivery/my?lat={user_lat}&lng={user_lng}"))  \
            .props("flat").classes("btn-my-deliveries"):
            num_orders = len(get_orders_for_delivery_person(user_id))
            if num_orders > 0:
                    ui.label(str(num_orders)).classes("order-badge")

    with ui.column().classes("w-full items-center text-center py-8 px-4"):
        ui.label(f"{t('order_details', lang_cookie)}{order_id}").classes("text-2xl font-bold mt-8 text-center")

        order_details = get_order_details(order_id)

        with ui.row().classes('w-full lg:grid lg:grid-cols-12 gap-6 mt-6'):
            # === Colonne gauche : information livraison ===
            with ui.column().classes('w-full lg:col-span-4 gap-4'):
                
                # === Détails de la commande ===
                with ui.card().classes('w-full p-4'):
                    ui.label(t("order_summary", lang_cookie)).classes("text-xl font-bold mb-4")
                    ui.label(f"{t('client_name', lang_cookie)}{order_details['customer']}").classes("mb-2")
                    ui.label(f"{t('delivery_address', lang_cookie)}{order_details['address']}").classes("mb-2")
                    ui.label(f"{t('order_date', lang_cookie)}{order_details['date']}").classes("mb-2")
                    ui.label(t("items_ordered", lang_cookie)).classes("font-bold mt-4 mb-2")

                    for item in order_details['items']:
                        product_name = get_product(item['product_id'])['name']
                        qty = item['qty']
                        pharmacy_name = get_pharmacy(item['pharmacy_id'])['name']
                        ui.label(f"• {product_name} x{qty} ({t('from_pharmacy', lang_cookie)}: {pharmacy_name})").classes("mb-1")

                    ui.label(f"{t('delivery_cost', lang_cookie)}{order_details['delivery_cost']:.2f}€").classes("mt-4")
                    ui.label(f"{t('total_cost', lang_cookie)}{order_details['total']:.2f}€").classes("font-bold mt-2")

                # valider la livraison
                def confirm_delivery():

                    """ Confirme la livraison de la commande. """

                    max_order = int(get_setting('max_order_delivery', 2))

                    if take_order(order_id, delivery_person_id=user_id, max_order=max_order):
                        ui.notify(t("delivery_confirmed", lang_cookie), color="green")
                    else:
                        ui.notify(t("error_confirming_delivery", lang_cookie), color="red")

                ui.button(t("confirm_delivery", lang_cookie), on_click=confirm_delivery) \
                    .classes("btn-primary w-full mt-4")
        
            # === Colonne droite : itinéraire ===
            with ui.column().classes('w-full lg:col-span-8'):
                
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