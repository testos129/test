from nicegui import ui, app
from fastapi import Request
from fastapi.responses import RedirectResponse
import json

from components.theme import apply_background
from components.navbar_delivery import navbar_delivery
from services.auth import get_current_user, sessions
from services.users import get_user_info, get_orders_for_delivery_person, cancel_order_delivery, get_order_details
from services.items import get_pharmacy
from services.distance import optimize_route
from translations.translations import t

from services.file_io import load_yaml
functionalities_switch = load_yaml('components/functionalities_switch.yaml')
ALLOW_DELIVERY_CANCEL = functionalities_switch.get('ALLOW_DELIVERY_CANCEL', True)


@ui.page("/delivery/my")
def delivery_order_page(request: Request):

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
    # Retour à l'accueil livreur 
    ui.button(t("return_home", lang_cookie), on_click=lambda: ui.navigate.to("/delivery/home")).classes("btn-back")

    in_progress_orders = get_orders_for_delivery_person(user_id)

    if not in_progress_orders:
        with ui.row().classes("justify-center w-full mt-4"):
            ui.label(t("no_in_progress_orders", lang_cookie)).classes("text-lg text-center")
    else:
        with ui.row().classes("justify-center w-full mt-4"):
            ui.label(t("my_in_progress_orders", lang_cookie)).classes("text-2xl font-bold text-center")

        # === Récupération des coordonnées utilisateur depuis les paramètres d'URL ===
        params = request.query_params
        user_lat = float(params.get('lat'))
        user_lng = float(params.get('lng'))

        # Initialisation si elle n'existe pas encore
        if not hasattr(ui.state, "current_order"):
            ui.state.current_order = in_progress_orders[0]["order_id"] if in_progress_orders else None

        # Fonction pour mettre à jour
        def update_current_order(order_id):
            ui.state.current_order = order_id
            ui.navigate.reload()  # recharge l'UI avec la nouvelle valeur

        with ui.row().classes('w-full lg:grid lg:grid-cols-12 gap-6 mt-6'):

            # === Colonne gauche : card commande ===
            with ui.column().classes('w-full lg:col-span-4 gap-4'):
                for order in in_progress_orders:
                    order_id = order['order_id']
                    with ui.card().classes("w-full mt-4 hover:bg-gray-100 transition-colors duration-200"):
                        clickable_zone = ui.element("div") \
                            .classes("w-full cursor-pointer p-2 hover:bg-gray-50 rounded-lg transition-colors duration-150") \
                            .on('click', lambda e, oid=order_id: update_current_order(oid))
                        with clickable_zone:
                            ui.label(f"{t('commande_num', lang_cookie)}{order_id}").classes("font-bold")
                            ui.label(f"{t('client_name', lang_cookie)}{order['customer']}")
                            ui.label(f"{t('delivery_address', lang_cookie)}{order['address']}")
                            total_cost_product = order['total'] - order['delivery_cost']
                            ui.label(f"{t('total_cost_product', lang_cookie)}{total_cost_product:.2f}€").classes("font-bold mt-2")
                            ui.label(f"{t('fees', lang_cookie)}{order['delivery_cost']//2:.2f}€").classes("font-bold mt-2")

                        with ui.expansion(t("details", lang_cookie)) \
                            .classes("w-full") \
                            .on('click.stop', None):  # stoppe la propagation du clic à la card
                            # Regrouper les produits par pharmacie
                            pharmacies = {}
                            for item in order["items"]:
                                pid = item["pharmacy_id"]
                                if pid not in pharmacies:
                                    pharmacies[pid] = []
                                pharmacies[pid].append(item)

                            # Afficher chaque pharmacie et ses produits
                            for pharmacy_id, items in pharmacies.items():
                                pharmacy_info = get_pharmacy(pharmacy_id)
                                total_pharma = sum(i["qty"] * i["price"] for i in items)

                                with ui.expansion(f"🏥 {pharmacy_info['name']}\n{t('address_2', lang_cookie)} {pharmacy_info['address']}", value=True)  \
                                    .classes("ml-2 w-full whitespace-pre-line"):
                                    for item in items:
                                        with ui.row().classes("justify-between text-sm text-gray-700 px-2"):
                                            ui.label(f"{item['name']} (x{item['qty']})")
                                            ui.label(f"{item['price'] * item['qty']:.2f}€")
                                    ui.label(f"{t('total_2', lang_cookie)}{total_pharma:.2f}€").classes("text-sm text-gray-700")

                        def cancel_delivery(oid):

                            """ Annule la livraison de la commande. """

                            if cancel_order_delivery(oid):
                                ui.notify(t("delivery_cancelled", lang_cookie), color="green")
                                ui.navigate.reload()
                            else:
                                ui.notify(t("error_cancelling_delivery", lang_cookie), color="red")

                        if ALLOW_DELIVERY_CANCEL: # Permet de désactiver l'option d'annuler une commande
                            ui.button(t("cancel_delivery", lang_cookie), on_click=lambda oid=order_id: cancel_delivery(oid)).classes("btn-cancel-order mr-2")


            # === Colonne droite : itinéraire ===
            with ui.column().classes('w-full lg:col-span-8'):

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