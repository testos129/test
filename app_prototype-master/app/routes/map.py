from nicegui import ui, app
from fastapi.responses import RedirectResponse
import json
from fastapi import Request

from app.components.navbar import navbar
from app.components.theme import apply_background
from app.services.auth import get_current_user, sessions
from app.services.users import record_visit, get_user_info
from app.services.items import get_product, get_pharmacy, get_pharmacies_with_product, get_min_price_for_product
from app.translations.translations import t


@ui.page('/product/{product_id}/map')
def product_map(product_id: str, request: Request):

    """Page d'affichage de la carte avec les pharmacies vendant le produit donné."""

    # === Setup initial ===

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    if not get_current_user():
        return RedirectResponse('/')
    
    token = app.storage.browser.get('token')
    user_id = sessions[token]

    user_info = get_user_info(user_id)
    if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):  # utilisateur non confirmé et non admin
        return RedirectResponse('/')

    record_visit(user_id, f'/product/{product_id}')   # Page incluse dans l'historique de navigation

    apply_background()
    navbar(request)

    lang_cookie = request.cookies.get("language", "fr")
    distance_cookie = float(request.cookies.get("max_distance", "10"))

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


    # === Récupération de toutes les pharmacies qui proposent le produit ===
    pharmacies_with_product = get_pharmacies_with_product(int(product_id))

    pharmacies_js = []
    for entry in pharmacies_with_product:
        pharmacie = get_pharmacy(entry["id"])
        if pharmacie and "coords" in pharmacie:
            pharmacies_js.append({
                "name": pharmacie["name"],
                "lat": pharmacie["coords"]["lat"],
                "lng": pharmacie["coords"]["lng"],
                "price": f"{entry['price']:.2f}",
                "stock": entry["qty"]
            })


    # === Script d’affichage Leaflet natif avec popups ===
    ui.run_javascript(f"""
        setTimeout(function() {{
            var map = L.map('map').setView([{pharmacie["coords"]["lat"]}, {pharmacie["coords"]["lng"]}], 14);

            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                maxZoom: 19
            }}).addTo(map);

            var pharmacies = {json.dumps(pharmacies_js)};
            pharmacies.forEach(function(ph) {{
                L.marker([ph.lat, ph.lng])
                    .addTo(map)
                    .bindTooltip("💊 " + ph.name + " (" + ph.price + " €)", {{
                        permanent: true,
                        direction: "top",
                        offset: [0, -10]
                    }})
                    .openTooltip();
            }});
        }}, 400);
    """)


    # === Bloc itinéraire flottant ===
    show_block = {"visible": False}

    @ui.refreshable
    def itinerary_block():

        if show_block["visible"]:
            with ui.card().classes(
                'absolute top-16 right-4 bg-white p-4 shadow-lg rounded-xl w-72 z-[9999]'
            ):
                ui.label(t("compute_itinerary", lang_cookie)).classes('text-lg font-semibold mb-3 text-center')

                # === Option 1 : Géolocalisation ===
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
                                    alert("{t('pos_not_found', lang_cookie)}" + err.message);
                                }}
                            );
                        }} else {{
                            alert({t("geo_not_supported", lang_cookie)});
                        }}
                    """)

                ui.button(t("use_pos", lang_cookie), on_click=use_current_location)\
                    .classes('btn-secondary w-full mb-3')

                ui.separator().classes('my-2')

                # === Option 2 : saisie manuelle de l'adresse ===
                manual_input = ui.input(
                    label=t("enter_addr", lang_cookie)
                ).props('outlined clearable').classes('w-full mb-2')

                ui.button(t("validate_addr", lang_cookie), on_click=lambda: ui.navigate.to(
                    f"/product/{product_id}/itinerary?address={manual_input.value}"
                )).classes('btn-success w-full')

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