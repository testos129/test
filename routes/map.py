from nicegui import ui, app
from fastapi.responses import RedirectResponse
import json
from fastapi import Request

from components.navbar import navbar
from components.footer import footer_bar
from components.theme import apply_background
from services.auth import get_current_user
from services.users import record_visit, get_user_info, update_user
from services.items import get_product, get_pharmacy, get_pharmacies_with_product, get_min_price_for_product, get_all_pharmacies
from services.distance import haversine_dist, distance_by_day
from services.address import get_coords_from_address
from services.logging_setup import get_logger
from translations.translations import t

from services.file_io import load_yaml
functionalities_switch = load_yaml('components/functionalities_switch.yaml')
ENABLE_MAX_DISTANCE_PHARMACY = functionalities_switch.get('ENABLE_MAX_DISTANCE_PHARMACY', True)
ENABLE_SET_DISTANCE_LIMIT = functionalities_switch.get('ENABLE_SET_DISTANCE_LIMIT', True)
ENABLE_USE_STOCK_MODE = functionalities_switch.get('ENABLE_USE_STOCK_MODE', True)


@ui.page('/product/{product_id}/map')
def product_map(product_id: str, request: Request):

    """Page d'affichage de la carte avec les pharmacies vendant le produit donné."""

    # === Setup initial ===

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for page map: no valid token, ip: {host}")
        return RedirectResponse('/')
    
    logger = get_logger('nav')

    user_info = get_user_info(user_id)
    if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):  # utilisateur non confirmé et non admin
        logger.info("Access denied for page map: not confirmed", extra={"user_id": user_id})
        return RedirectResponse('/')

    record_visit(user_id, f'/product/{product_id}')   # Page incluse dans l'historique de navigation

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
            t("return_product", lang_cookie),
            on_click=lambda pid=product_id: ui.navigate.to(f'/product/{pid}')
        ).classes('btn-back')


    # === Récupération de la pharmacie de référence (la moins chère qui vend le produit) ===
    pharmacies = get_pharmacies_with_product(int(product_id))
    if not pharmacies:
        ui.label(t("no_pharmacies", lang_cookie)).classes('text-red-500 text-xl fade-in')
        return

    pharmacie = get_pharmacy(get_min_price_for_product(int(product_id))["pharmacy_id"]) # On prend cette pharmacie pour centrer l'affichage


    # === Récupération du produit ===
    product = get_product(int(product_id))
    if not product:
        ui.label(t("no_product", lang_cookie)).classes('text-red-500 text-xl fade-in')
        return
    
    ui.label(f"{t('map', lang_cookie)} {product['name']}").classes('text-2xl font-bold text-center mt-4 fade-in')


    # === Charger Leaflet natif ===
    ui.add_head_html("""
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    """)


    # === Conteneur de la carte ===
    ui.element('div').props('id=map').style(
        'width: 100%; height: 600px; border-radius: 12px; margin-top: 10px;'
    )

    # === Trouver les coordonnées des adresses enregistrées ===
    coords_address_1 = None
    coords_address_2 = None

    if user_info['main_address_street'] and user_info['main_address_city'] and user_info['main_address_postal_code']:
        search_address_1 = user_info['main_address_street'] + ", " + user_info['main_address_postal_code'] + ", " + user_info['main_address_city']
        search_result_1 = get_coords_from_address(search_address_1)
        if search_result_1[0]:
            coords_address_1 = search_result_1[1][0], search_result_1[1][1]
    
    if user_info['secondary_address_street'] and user_info['secondary_address_city'] and user_info['secondary_address_postal_code']:
        search_address_2 = user_info['secondary_address_street'] + ", " + user_info['secondary_address_postal_code'] + ", " + user_info['secondary_address_city'] 
        search_result_2 = get_coords_from_address(search_address_2)
        if search_result_2[0]:
            coords_address_2 = search_result_2[1][0], search_result_2[1][1]


    # === Récupération de toutes les pharmacies qui proposent le produit ===
    if ENABLE_USE_STOCK_MODE:
        pharmacies_with_product = get_pharmacies_with_product(int(product_id))
    else:  # mode no stock : toutes les pharmacies
        pharmacies_with_product = get_all_pharmacies()

    pharmacies_js = []
    for entry in pharmacies_with_product:
        pharmacie = get_pharmacy(entry["id"])
        if pharmacie and "coords" in pharmacie:

            pharmacy_data = {}

            # Distance par rapport aux coordonnées de l'utilisateur si récupérées
            if user_lat and user_lng:
                distance = haversine_dist(float(user_lat), float(user_lng), pharmacie["coords"]["lat"], pharmacie["coords"]["lng"])
                if distance <= distance_cookie or not ENABLE_MAX_DISTANCE_PHARMACY:  # check de distance seulement si la fonctionalité est activée
                    pharmacy_data = {
                        "name": pharmacie["name"],
                        "lat": pharmacie["coords"]["lat"],
                        "lng": pharmacie["coords"]["lng"],
                        "dist": distance
                        }
                    
                    if ENABLE_USE_STOCK_MODE:  # En stock mode uniquement, ajout du prix et de la quantité disponible
                        pharmacy_data['price'] = f"{entry['price']:.2f}"
                        pharmacy_data['stock'] = entry["qty"]

            # Distance par rapport à l'adresse principale si définie
            if coords_address_1:
                distance = haversine_dist(float(coords_address_1[0]), float(coords_address_1[1]), pharmacie["coords"]["lat"], pharmacie["coords"]["lng"])
                if distance <= distance_cookie or not ENABLE_MAX_DISTANCE_PHARMACY:
                    if pharmacy_data and distance < pharmacy_data['dist']:
                        pharmacy_data['dist'] = distance
                    else:
                        pharmacy_data = {
                            "name": pharmacie["name"],
                            "lat": pharmacie["coords"]["lat"],
                            "lng": pharmacie["coords"]["lng"],
                            "dist": distance
                            }
                        
                        if ENABLE_USE_STOCK_MODE:
                            pharmacy_data['price'] = f"{entry['price']:.2f}"
                            pharmacy_data['stock'] = entry["qty"]
            
            # Distance par rapport à l'adresse secondaire si définie
            if coords_address_2:
                distance = haversine_dist(float(coords_address_2[0]), float(coords_address_2[1]), pharmacie["coords"]["lat"], pharmacie["coords"]["lng"])
                if distance <= distance_cookie or not ENABLE_MAX_DISTANCE_PHARMACY:
                    if pharmacy_data and distance < pharmacy_data['dist']:
                        pharmacy_data['dist'] = distance
                    else:
                        pharmacy_data = {
                            "name": pharmacie["name"],
                            "lat": pharmacie["coords"]["lat"],
                            "lng": pharmacie["coords"]["lng"],
                            "dist": distance
                            }
                        
                        if ENABLE_USE_STOCK_MODE:
                            pharmacy_data['price'] = f"{entry['price']:.2f}"
                            pharmacy_data['stock'] = entry["qty"]

            # ajout seulement si non dictionaire vide
            if pharmacy_data:  
                pharmacies_js.append(pharmacy_data)

    if pharmacies_js: # si au moins une pharmacie trouvée
    
        pharmacies_js = sorted(pharmacies_js, key=lambda ph: ph.get("dist", float("inf")))[:5]  # 5 plus proches d'un des points utilisateur
        
        # Création de variables intermédiaires pour éviter les erreurs dans la f-string du js en cas de None
        if coords_address_1:  
            lat_address_1, lng_address_1 = coords_address_1
        else:
            lat_address_1, lng_address_1 = None, None 
        if coords_address_2:
            lat_address_2, lng_address_2 = coords_address_2
        else:
            lat_address_2, lng_address_2 = None, None


        # === Script d’affichage Leaflet natif avec popups ===
        position_text = t("your_position", lang_cookie)
        addr_1_text = t("your_principal_addr", lang_cookie)
        addr_2_text = t("your_secondary_addr", lang_cookie)


        ui.run_javascript(f"""
            setTimeout(function() {{
                var map = L.map('map').setView([{pharmacie["coords"]["lat"]}, {pharmacie["coords"]["lng"]}], 14);

                L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                    maxZoom: 19
                }}).addTo(map);

                var pharmacies = {json.dumps(pharmacies_js)};
                pharmacies.forEach(function(ph) {{
                    var tooltipText = "💊 " + ph.name;
                    if (ph.price !== undefined && ph.price !== null) {{
                        tooltipText += " (" + parseFloat(ph.price).toFixed(2) + " €)";
                    }}

                    L.marker([ph.lat, ph.lng])
                        .addTo(map)
                        .bindTooltip(tooltipText, {{
                            permanent: true,
                            direction: "top",
                            offset: [0, -10]
                        }})
                        .openTooltip();
                }});

                // === Marqueurs rouges position et adresses ===
                var userIcon = L.icon({{
                    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
                    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.3/images/marker-shadow.png',
                    iconSize: [25, 41],
                    iconAnchor: [12, 41],
                    popupAnchor: [1, -34],
                    shadowSize: [41, 41]
                }});

                if ({'true' if (user_lat is not None and user_lng is not None) else 'false'}) {{
                    var userMarker = L.marker([{user_lat or 0}, {user_lng or 0}], {{ icon: userIcon }}).addTo(map);
                    userMarker.bindTooltip("{position_text}", {{
                        permanent: true,
                        direction: "top",
                        offset: [0, -10]
                    }})
                    .openTooltip();
                }}

                if ({'true' if (lat_address_1 is not None and lng_address_1 is not None) else 'false'}) {{
                    var userMarker = L.marker([{lat_address_1 or 0}, {lng_address_1 or 0}], {{ icon: userIcon }}).addTo(map);
                    userMarker.bindTooltip("{addr_1_text}", {{
                        permanent: true,
                        direction: "top",
                        offset: [0, -10]
                    }})
                    .openTooltip();
                }}

                if ({'true' if (lat_address_2 is not None and lng_address_2 is not None) else 'false'}) {{
                    var userMarker = L.marker([{lat_address_2 or 0}, {lng_address_2 or 0}], {{ icon: userIcon }}).addTo(map);
                    userMarker.bindTooltip("{addr_2_text}", {{
                        permanent: true,
                        direction: "top",
                        offset: [0, -10]
                    }})
                    .openTooltip();
                }}
            }}, 400);
        """)


        # === Bloc itinéraire flottant ===
        show_block = {"visible": False}

        @ui.refreshable
        def itinerary_block():

            """Construction du block de lancement de l'itinéraire à partir de la position ou d'une adresse"""

            if show_block["visible"]:
                with ui.card().classes(
                    'absolute top-16 right-4 bg-white p-4 shadow-lg rounded-xl w-72 z-[9999]'
                ):
                    ui.label(t("compute_itinerary", lang_cookie)).classes('text-lg font-semibold mb-3 text-center')

                    # === Option 1 : Géolocalisation ===
                    pos_not_found = t("pos_not_found", lang_cookie)
                    geo_not_supported = t("geo_not_supported", lang_cookie)
                    
                    def use_current_location():

                        ui.run_javascript(f"""
                            if (navigator.geolocation) {{
                                navigator.geolocation.getCurrentPosition(
                                    function(pos) {{
                                        const lat = pos.coords.latitude;
                                        const lng = pos.coords.longitude;
                                        window.location.href = `/product/{product_id}/itinerary?lat=${{lat}}&lng=${{lng}}`;
                                    }},
                                    function(err) {{
                                        alert("{pos_not_found}: " + err.message);
                                    }}
                                );
                            }} else {{
                                alert("{geo_not_supported}");
                            }}
                        """)

                    ui.button(t("use_pos", lang_cookie), on_click=use_current_location)\
                        .classes('btn-secondary w-full mb-3')

                    # === Option 2 : adresse déjà définie ===
                    if user_info['main_address_street'] and user_info['main_address_city'] and user_info['main_address_postal_code']:
                        search_address_1 = user_info['main_address_street'] + ", " + user_info['main_address_postal_code'] + ", " + user_info['main_address_city']
                        ui.button(f"{search_address_1}", on_click=lambda: ui.navigate.to(f"/product/{product_id}/itinerary?address={search_address_1}")) \
                        .classes('btn-secondary w-full mb-3')

                    if user_info['secondary_address_street'] and user_info['secondary_address_city'] and user_info['secondary_address_postal_code']:
                        search_address_2 = user_info['secondary_address_street'] + ", " + user_info['secondary_address_postal_code'] + ", " + user_info['secondary_address_city'] 
                        ui.button(f"{search_address_2}", on_click=lambda: ui.navigate.to(f"/product/{product_id}/itinerary?address={search_address_2}")) \
                        .classes('btn-secondary w-full mb-3')

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

                            if not user_info['main_address_street']:  # Pas encore d'adresse définie
                                update_user(user_id, 
                                            main_address_street=address_input.value, 
                                            main_address_city=city_input.value, 
                                            main_address_postal_code=postal_code_input.value)
                                logger.info("Main address updated after an itinerary search", extra={"user_id": user_id})
                                
                            search_address = address_input.value + ", " + postal_code_input.value + ", " + city_input.value
                            ui.navigate.to(f"/product/{product_id}/itinerary?address={search_address}")

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

        def toggle_block():
            
            show_block["visible"] = not show_block["visible"]
            itinerary_block.refresh()

        # Bouton itinéraire
        ui.button(
            t("itinerary", lang_cookie),
            on_click=toggle_block
        ).classes(
            'btn-secondary absolute top-4 right-4 bg-blue-600 text-white shadow-lg rounded-full p-3 z-[9999]'
        )

        itinerary_block()

    else:
        ui.notify(t("no_pharmacy", lang_cookie), color='negative')