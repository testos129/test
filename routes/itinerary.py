from nicegui import ui, app
from fastapi.responses import RedirectResponse
from fastapi import Request
import requests
from urllib.parse import unquote
import json

from components.navbar import navbar
from components.footer import footer_bar
from components.theme import apply_background
from services.auth import get_current_user
from services.users import record_visit, get_user_info
from services.distance import haversine_dist, distance_by_day
from services.items import get_product, get_pharmacies_with_product, get_pharmacy, get_all_pharmacies
from services.address import get_coords_from_address
from services.logging_setup import get_logger
from translations.translations import t

from services.file_io import load_yaml
functionalities_switch = load_yaml('components/functionalities_switch.yaml')
ENABLE_MAX_DISTANCE_PHARMACY = functionalities_switch.get('ENABLE_MAX_DISTANCE_PHARMACY', True)
ENABLE_SET_DISTANCE_LIMIT = functionalities_switch.get('ENABLE_SET_DISTANCE_LIMIT', True)
ENABLE_USE_STOCK_MODE = functionalities_switch.get('ENABLE_USE_STOCK_MODE', True)


@ui.page('/product/{product_id}/itinerary')
def product_itinerary(request: Request, product_id: str):

    """Page affichant l'itinéraire optimisé vers la pharmacie la plus proche pour un produit donné."""

    # === Setup initial ===

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for page itinerary: no valid token, ip: {host}")
        return RedirectResponse('/')
    
    logger = get_logger('nav')

    user_info = get_user_info(user_id)
    if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):  # utilisateur non confirmé et non admin
        logger.info("Access denied for page itinerary: not confirmed", extra={"user_id": user_id})
        return RedirectResponse('/')

    record_visit(user_id, f'/product/{product_id}/itinerary')   # Page incluse dans l'historique de navigation

    apply_background()
    navbar(request)
    footer_bar(request)

    lang_cookie = request.cookies.get("language", "fr")

    if ENABLE_SET_DISTANCE_LIMIT:  # Functionality switch pour laisser à l'utilisateur le choix de la distance max de recherche
        distance_cookie = float(request.cookies.get("max_distance", distance_by_day()))
    else:
        distance_cookie = distance_by_day()

    user_lat = request.cookies.get("user_lat")
    user_lng = request.cookies.get("user_lng")


    async def use_current_location():

        """Demande la géolocalisation sans bloquer le rendu."""

        js_code = """
        new Promise((resolve, reject) => {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    pos => {
                        const lat = pos.coords.latitude;
                        const lng = pos.coords.longitude;

                        // Stocker les coordonnées dans les cookies pour 1 heure
                        document.cookie = `user_lat=${lat}; path=/; max-age=3600; SameSite=Lax`;
                        document.cookie = `user_lng=${lng}; path=/; max-age=3600; SameSite=Lax`;
                        location.reload(); // recharge la page pour que Python voie les cookies

                        // Résoudre la promesse avec les coordonnées
                        resolve({lat, lng});
                    },
                    err => reject("Erreur: " + err.message)
                );
            } else {
                reject("La géolocalisation n'est pas supportée par ce navigateur.");
            }
        });
        """
        try:
            await ui.run_javascript(js_code, timeout=10.0)
        except Exception as e:
            ui.notify(f"Erreur géolocalisation : {e}", color="red")
            print("❌ Erreur géoloc:", e)

    # Lancer la géoloc sans bloquer le rendu initial
    if not request.cookies.get("user_lat") or not request.cookies.get("user_lng"):
        ui.timer(0.5, use_current_location, once=True)


    # Bouton retour
    with ui.row().classes('w-full p-4 items-center'):
        ui.button(
            t("return_map", lang_cookie),
            on_click=lambda pid=product_id: ui.navigate.to(f'/product/{pid}/map')
        ).classes('btn-back')


    # === Titre de la page ===
    product = get_product(int(product_id))
    if not product:
        ui.label(t("no_product", lang_cookie)).classes('text-red-500 text-xl')
        return
    ui.label(f"{t('optimized_itinerary', lang_cookie)}{product['name']}")\
        .classes('text-2xl font-bold mt-2 mb-4 text-center')


    # === Récupération des paramètres dans l'URL ===
    params = request.query_params
    lat = params.get('lat')
    lng = params.get('lng')
    address = params.get('address')


    # === Gestion du cas où l'adresse est fournie directement (sans les coordonnées) ===
    if address and not lat and not lng:

        result_address = get_coords_from_address(address)
        if result_address[0]:
            lat, lng = result_address[1]
        else:
            if result_address[1] == "no_addr_found":
                ui.label(t("no_addr_found", lang_cookie)).classes('text-red-500 text-lg italic')
                return
            else:
                ui.label(f"{'error_geocoding', lang_cookie}{result_address[2]}").classes('text-red-500')
                return

    if not lat or not lng:
        ui.label(t("missing_coords", lang_cookie))\
            .classes('text-red-500')
        return

    lat = float(lat)
    lng = float(lng)


    # === Trouver les pharmacies avec le produit ===
    if ENABLE_USE_STOCK_MODE:
        pharmacy_ids = get_pharmacies_with_product(int(product_id))
    else:  # mode no stock : toutes les pharmacies
        pharmacy_ids = get_all_pharmacies()

    pharmacies_with_product = [
        {
            "name": get_pharmacy(pharmacie['id'])["name"],
            "lat": get_pharmacy(pharmacie['id'])["coords"]["lat"],
            "lng": get_pharmacy(pharmacie['id'])["coords"]["lng"]
        }
        for pharmacie in pharmacy_ids
    ]

    if not pharmacies_with_product:
        ui.label(t("no_pharmacies", lang_cookie)).classes('text-red-500')
        return
    

    if ENABLE_MAX_DISTANCE_PHARMACY:  # Filtre sur uniquement les pharmacies à une distance inférieure au seuil fixé de l'utilisateur
        pharmacies_with_product_filt = []
        for entry in pharmacies_with_product:

            if lat and lng:  # Filtre sur la distance par rapport à la requête
                distance = haversine_dist(float(lat), float(lng), entry["lat"], entry["lng"])
                if distance <= distance_cookie:
                    pharmacies_with_product_filt.append(entry)   
    else:
        pharmacies_with_product_filt = pharmacies_with_product
    
    pharmacies_sorted = sorted(
        pharmacies_with_product_filt,
        key=lambda ph: haversine_dist(lat, lng, ph["lat"], ph["lng"])
    )[:3]  # Limiter aux 3 pharmacies les plus proches pour éviter trop de calculs


    # === Conteneur carte + overlay ===
    with ui.element('div').props('id=map-container').style(
        'position: relative; width: 100%; height: 600px; border-radius: 12px; margin-top: 10px;'
    ):
        ui.element('div').props('id=map').style(
            'width: 100%; height: 100%; border-radius: 12px;'
        )
        ui.html(f"""
            <div id="loading-overlay">
                <div class="spinner"></div>
                {t("computing_itinerary", lang_cookie)}
            </div>
        """)


    # === CSS overlay + spinner ===
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
                z-index: 9999; /* passe au-dessus de la carte */
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
        </style>
    """)


    # === Charger Leaflet et Routing Machine ===
    ui.add_head_html("""
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <link rel="stylesheet" href="https://unpkg.com/leaflet-routing-machine@3.2.12/dist/leaflet-routing-machine.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script src="https://unpkg.com/leaflet-routing-machine@3.2.12/dist/leaflet-routing-machine.js"></script>
    """)


    #  === Script JS : calcule le trajet le plus rapide ===
    starting_point_message = t("starting_point", lang_cookie)

    ui.run_javascript(f"""
        setTimeout(function() {{
            var map = L.map('map').setView([{lat}, {lng}], 14);

            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                maxZoom: 19,
                detectRetina: true,
                crossOrigin: true
            }}).addTo(map);

            var pharmacies = {json.dumps(pharmacies_with_product_filt)};
            var pharmacies_search = {json.dumps(pharmacies_sorted)};
            var shortestTime = Infinity;
            var bestRoute = null;

            // Marqueurs pharmacies
            pharmacies.forEach(function(ph) {{
                L.marker([ph.lat, ph.lng]).addTo(map).bindPopup("💊 " + ph.name);
            }});

            // Marqueur départ
            L.marker([{lat}, {lng}]).addTo(map).bindPopup("{starting_point_message}").openPopup();

            var overlay = document.getElementById("loading-overlay");
            if (overlay) overlay.style.display = "flex";

            // Sécurité : timeout pour ne pas spinner indéfiniment (10s)
            var spinnerTimeout = setTimeout(function() {{
                console.warn("⏱️ Timeout itinéraire atteint — arrêt du spinner");
                if (overlay) overlay.style.display = "none";
            }}, 10000);

            function checkNextPharmacy(index) {{
                if (index >= pharmacies_search.length) {{
                    if (bestRoute) {{
                        L.Routing.control({{
                            waypoints: bestRoute,
                            router: L.Routing.osrmv1({{
                                serviceUrl: 'https://router.project-osrm.org/route/v1'
                            }}),
                            routeWhileDragging: false,
                            addWaypoints: false,
                            createMarker: function() {{ return null; }}
                        }}).addTo(map);
                        console.log("✅ Meilleur itinéraire trouvé :", bestRoute);
                    }} else {{
                        console.warn("⚠️ Aucun itinéraire valide trouvé");
                    }}
                    if (overlay) overlay.style.display = "none";
                    clearTimeout(spinnerTimeout);
                    return;
                }}

                var ph = pharmacies_search[index];
                console.log("🧭 Calcul de l'itinéraire vers", ph.name);

                var control = L.Routing.control({{
                    waypoints: [
                        L.latLng({lat}, {lng}),
                        L.latLng(ph.lat, ph.lng)
                    ],
                    router: L.Routing.osrmv1({{
                        serviceUrl: 'https://router.project-osrm.org/route/v1'
                    }}),
                    routeWhileDragging: false,
                    addWaypoints: false,
                    createMarker: function() {{ return null; }}
                }})
                .on('routesfound', function(e) {{
                    var travelTime = e.routes[0].summary.totalTime;
                    if (travelTime < shortestTime) {{
                        shortestTime = travelTime;
                        bestRoute = [
                            L.latLng({lat}, {lng}),
                            L.latLng(ph.lat, ph.lng)
                        ];
                    }}
                    map.removeControl(control);
                    checkNextPharmacy(index + 1);
                }})
                .on('routingerror', function(err) {{
                    console.error("🚫 Erreur de routage vers", ph.name, err);
                    map.removeControl(control);
                    checkNextPharmacy(index + 1);
                }})
                .addTo(map);

                try {{
                    control.route();
                }} catch (err) {{
                    console.error("❌ Exception pendant le routage :", err);
                    map.removeControl(control);
                    checkNextPharmacy(index + 1);
                }}
            }}

            checkNextPharmacy(0);
        }}, 500);
        """)