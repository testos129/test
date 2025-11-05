from nicegui import ui, app
from fastapi.responses import RedirectResponse
import random
from fastapi import Request

from app.components.theme import apply_background
from app.components.navbar import navbar
from app.services.auth import get_current_user, sessions
from app.services.items import get_tag_color, search_filter_product, get_min_price_for_product, get_filter_options, count_products_in_price_range
from app.services.reviews import get_average_rating, get_number_of_reviews
from app.services.users import record_visit, add_panier_item, get_user_info
from app.recommendations.recommendations import recommend_products
from app.recommendations.user_product_matrix import update_interaction
from app.translations.translations import t

from app.services.file_io import load_yaml
functionalities_switch = load_yaml('components/functionalities_switch.yaml')
FILTER_PRODUCT_REVIEWS_ENABLED = functionalities_switch.get('FILTER_PRODUCT_REVIEWS_ENABLED', True)
FILTER_PRICE_DISPLAY_ENABLED = functionalities_switch.get('FILTER_PRICE_DISPLAY_ENABLED', True)
ENABLE_FILTER_PROVIDER_NAME = functionalities_switch.get('ENABLE_FILTER_PROVIDER_NAME', True)
DISPLAY_TAGS_ENABLED = functionalities_switch.get('DISPLAY_TAGS_ENABLED', True)


@ui.page('/home')
def home_page(request: Request):

    """Page d'accueil après connexion : permet de rechercher des produits, voir des recommandations, et filtrer par tags."""

    # === Setup initial ===

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    if not get_current_user():
        return RedirectResponse('/')

    token = app.storage.browser.get('token')
    user_id = sessions[token]

    # user_id = get_current_user(request)
    # if not user_id:
    #     print(request.cookies.get("session_token"))
    #     print(sessions)
    #     return RedirectResponse('/')

    user_info = get_user_info(user_id)
    if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):  # utilisateur non confirmé et non admin
        return RedirectResponse('/')
    
    record_visit(user_id, '/home')

    # Styles globaux + navbar + cookies
    apply_background()
    navbar(request)

    lang_cookie = request.cookies.get("language", "fr")
    distance_cookie = float(request.cookies.get("max_distance", "10"))


    selected_tags: list[str] = []
    selected_filters = {"categories": set(), "ages": set(), "providers": set(), "prices": set()}

    class PaginationState:
        def __init__(self):
            self.current_page = 0
            self.items_per_page = 15

    state = PaginationState()
    expanded_state = [False, False, False, False]  # état d'expansion des sections de la sidebar


    # === Fonctions utilitaires ===
    def pick_random_recommendation():

        """Fonction de proposition de recommandation (aléatoire parmi les recommandations)"""

        recommended_list = recommend_products(get_current_user())
        if not recommended_list:
            ui.notify(t("no_reco", lang_cookie), color='red')
            return
        product = random.choice(recommended_list)
        ui.navigate.to(f"/product/{product['id']}")

    def update_selection(filter_type, value, checked):
        
        """Met à jour les filtres sélectionnés et rafraîchit l'affichage."""

        if checked:
            selected_filters[filter_type].add(value)
        else:
            selected_filters[filter_type].discard(value)
        reset_page()  # applique aussi refresh_products()

    def clear_all_tags():

        """Efface tous les tags sélectionnés et rafraîchit l'affichage."""

        selected_tags.clear()
        render_selected_tags()
        reset_page()

    def remove_tag(tag: str):

        """Retire un tag sélectionné et rafraîchit l'affichage."""

        if tag in selected_tags:
            selected_tags.remove(tag)
        ui.timer(0, lambda: render_selected_tags())  # Pour éviter une erreur en détruisant l'objet en même temps que son parent
        reset_page()

    def add_tag(tag: str):

        """Ajoute un tag sélectionné et rafraîchit l'affichage."""

        if tag not in selected_tags:
            selected_tags.append(tag)
        render_selected_tags()
        reset_page()

    def change_page(delta: int):

        """Change la page courante et rafraîchit l'affichage."""

        state.current_page += delta
        refresh_products()

    def reset_page():

        """Remet la page courante à 0 et rafraîchit l'affichage."""

        state.current_page = 0
        refresh_products()


    # === Bandeau supérieur ===
    with ui.column().classes("relative w-full items-center text-center py-8 px-4 fade-in hero"):

        # === Bouton "Recommandé pour moi" ===
        ui.button(t("recommended", lang_cookie), on_click=pick_random_recommendation) \
            .classes("absolute top-4 right-6 z-10 btn-recommended desktop-nav")
        
        # === Texte d’introduction ===
        ui.label(t("intro_1", lang_cookie)).classes("text-2xl md:text-3xl font-bold text-gray-900 mb-2 tracking-tight")
        ui.label(t("intro_2", lang_cookie)).classes("text-gray-600 mb-5")

        # === Barre de recherche ===
        with ui.row().classes("items-center justify-center gap-2 w-full max-w-3xl flex-wrap"):

            # Container relatif pour le champ et les suggestions
            with ui.column().classes("relative flex-1 min-w-[240px]"):

                # Champ de recherche
                search = ui.input(
                    placeholder=t("recherche", lang_cookie)
                ).props("outlined dense clearable").classes("w-full search-input white-input")

                with search.add_slot("prepend"):
                    ui.icon("search").classes("text-gray-500")

                # 🔹 Ajout ici du spinner dans le slot append
                with search.add_slot("append"):
                    search_spinner = ui.spinner(size="sm").classes("hidden text-gray-500 mr-2")

                # Suggestions sous le champ
                suggestions_box = ui.column().classes(
                    "absolute top-full left-0 bg-white rounded-xl shadow-md mt-1 hidden w-full z-10"
                )


    # === Layout principal ===
    with ui.row().classes("w-full items-start justify-start gap-6 px-6 mt-6"):

        # === Sidebar de filtre ===
        with ui.column().classes('relative'):
            sidebar_expanded = False  # True = visible, False = rétractée

            def toggle_sidebar():
                
                """Bascule l'état de la sidebar entre expand et collapse."""

                nonlocal sidebar_expanded
                sidebar_expanded = not sidebar_expanded
                refresh_sidebar()

            @ui.refreshable
            def refresh_sidebar():

                """Rafraîchit la sidebar en fonction de son état (expand/collapse)"""

                sidebar_container.clear()

                if sidebar_expanded:
                    with sidebar_container:
                        with ui.column().classes('w-[260px] flex-shrink-0 border border-gray-300 bg-gray-50 p-4 rounded-2xl shadow-sm transition-all duration-300'):
                            with ui.row().on('click', toggle_sidebar):
                                ui.label(t("search_filter", lang_cookie)).classes("text-lg font-semibold mb-2 cursor-pointer")

                            def toggle_expanded(i):
                                expanded_state[i] = True

                            # Catégories
                            with ui.expansion(t("search_category", lang_cookie), value=expanded_state[0]).classes("font-semibold"):
                                categories_sorted = sorted(get_filter_options('category'), key=lambda x: x[1], reverse=True)[:20]
                                for cat, count in categories_sorted:
                                    ui.checkbox(
                                        f"{t(cat, lang_cookie)} ({count})",
                                        value=cat in selected_filters["categories"],
                                        on_change=lambda e, c=cat, i=0: (toggle_expanded(i), update_selection("categories", c, e.value))
                                    )

                            # Ages
                            with ui.expansion(t("search_age_group", lang_cookie), value=expanded_state[1]).classes("font-semibold"):
                                ages_sorted = sorted(get_filter_options('age_group'), key=lambda x: x[1], reverse=True)[:20]
                                for age, count in ages_sorted:
                                    ui.checkbox(
                                        f"{t(age, lang_cookie)} ({count})",
                                        value=age in selected_filters["ages"],
                                        on_change=lambda e, a=age, i=1: (toggle_expanded(i), update_selection("ages", a, e.value))
                                    )

                            # Fournisseurs
                            if ENABLE_FILTER_PROVIDER_NAME: # Controle l'option de filtrer sur un fournisseur
                                with ui.expansion(t("search_provider", lang_cookie), value=expanded_state[2]).classes("font-semibold"):
                                    providers_sorted = sorted(get_filter_options('provider'), key=lambda x: x[1], reverse=True)[:20]
                                    for prov, count in providers_sorted:
                                        ui.checkbox(
                                            f"{prov} ({count})",
                                            value=prov in selected_filters["providers"],
                                            on_change=lambda e, p=prov, i=2: (toggle_expanded(i), update_selection("providers", p, e.value))
                                        )

                            # Prix
                            with ui.expansion(t("search_price", lang_cookie), value=expanded_state[3]).classes("font-semibold"):
                                price_ranges = [("0-5", 0, 5), ("5-10", 5, 10), ("10-20", 10, 20), ("20+", 20, 1e6)]
                                for label, mn, mx in price_ranges:
                                    count = count_products_in_price_range(mn, mx)
                                    ui.checkbox(
                                        f"{label} € ({count})",
                                        value=(mn, mx) in selected_filters["prices"],
                                        on_change=lambda e, mn=mn, mx=mx, i=3: (toggle_expanded(i), update_selection("prices", (mn, mx), e.value))
                                    )
                else:
                    # Sidebar réduite
                    with sidebar_container:
                        with ui.column().classes(
                            'w-[120px] flex-shrink-0 border border-gray-300 bg-gray-50 p-3 rounded-2xl shadow-sm items-center transition-all duration-300'):
                            ui.button(t("search_filter_2", lang_cookie), on_click=toggle_sidebar)  \
                                .props("flat unelevated").classes("w-full text-black text-sm font-medium px-4 py-2 rounded-xl bg-white hover:bg-gray-100 transition")

            sidebar_container = ui.column()  # conteneur refreshable de la sidebar
            refresh_sidebar()

        # === Contenu principal ===
        with ui.column().classes('flex-grow min-w-0'):
            # Tags sélectionnés
            selected_tags_container = ui.row().classes('gap-2 flex-wrap mb-4 w-full px-2 items-center')

            def render_selected_tags():

                """Met à jour l'affichage des tags sélectionnés dans le bandeau."""

                selected_tags_container.clear()
                with selected_tags_container:
                    if selected_tags:
                        ui.label(t("filters", lang_cookie)).classes("text-xs font-semibold text-gray-500 mr-1")
                    for select_tag in selected_tags:
                        color = get_tag_color(select_tag)
                        with ui.row().classes('tag-bubble cursor-pointer').style(f'background-color: {color}; color: white;'):
                            ui.label(select_tag).classes("font-medium")
                            ui.icon('close').classes('bubble-close cursor-pointer').on('click', lambda tag=select_tag: remove_tag(tag))
                    if selected_tags:
                        ui.button(t("remove", lang_cookie), on_click=clear_all_tags).props("flat").classes("text-xs text-gray-600 ml-2")

            render_selected_tags()

            # Container produits et pagination
            products_container = ui.grid().classes('w-full gap-5 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 items-start justify-center px-6 max-w-6xl mx-auto')
            pagination_container = ui.row().classes('justify-center gap-4 mt-6 w-full')


    # === Rafraîchissement uniquement des produits ===
    @ui.refreshable
    def refresh_products():

        """Rafraîchit uniquement la liste des produits en fonction des tags, filtres, recherche et pagination."""

        products_container.clear()
        pagination_container.clear()
        render_selected_tags()

        query = (search.value or "").lower()
        filtered_products = search_filter_product(query=query, selected_tags=selected_tags, selected_filters=selected_filters)

        # Pré-calcul des notes, reviews et prix pour accélérer
        ratings_cache = {p['id']: get_average_rating(p["id"]) for p in filtered_products}
        reviews_cache = {p['id']: get_number_of_reviews(p["id"]) for p in filtered_products}
        prices_cache = {p['id']: get_min_price_for_product(p["id"]) for p in filtered_products}

        filtered_products.sort(
            key=lambda p: (
                ratings_cache[p["id"]] is None,
                -(ratings_cache[p["id"]] or 0),
                -(reviews_cache[p["id"]] or 0)
            )
        )

        if not query:
            suggestions_box.classes("hidden")

        else:
            suggestions_box.clear()

            exact_match = any(
                query.strip().lower() == p['name'].strip().lower()
                for p in filtered_products
            )

            if exact_match:
                # Cache la liste si le champ correspond exactement à un produit
                suggestions_box.classes(add="hidden")
            
            else:
                for product in filtered_products[:5]:
                    with suggestions_box:

                        def make_click_handler(value=product['name']):
                            async def on_click():
                                search.value = value         # Remplit le champ
                                suggestions_box.classes(add='hidden')  # Cache le menu
                            return on_click
                        
                        ui.label(f"{product['name']}").classes("px-3 py-1 hover:bg-gray-100 cursor-pointer").on("mousedown.prevent", make_click_handler())  #.on("click", make_click_handler())
                suggestions_box.classes(remove='hidden')

            # === Ajoute focus/blur events une seule fois (au premier appel) ===
            if not hasattr(refresh_products, "_events_bound"):
                refresh_products._events_bound = True

                async def on_blur(e):
                    # petit délai pour ne pas fermer avant le clic
                    await ui.run_javascript("setTimeout(() => {}, 100)")
                    suggestions_box.classes(add="hidden")

                async def on_focus(e):
                    if (search.value or "").strip():
                        refresh_products.refresh()

                search.on("blur", on_blur)
                search.on("focus", on_focus)


        total_pages = max(1, (len(filtered_products) + state.items_per_page - 1) // state.items_per_page)
        start = state.current_page * state.items_per_page
        end = start + state.items_per_page
        paginated_products = filtered_products[start:end]

        # Affichage des cards des produits
        with products_container:
            for product in paginated_products:
                min_price = prices_cache[product['id']]
                price_txt = f"{min_price['price']:.2f} €" if min_price else "Indisponible"

                with ui.card().classes('product-card card-fixed hover-lift relative overflow-hidden'):
                    with ui.column().classes('cursor-pointer').on('click', lambda e, pid=product["id"]: ui.navigate.to(f'/product/{pid}')):
                        with ui.row().classes('product-header flex-row items-start gap-4'):
                            ui.image(product["image"]).classes('product-thumb w-24 h-24 flex-shrink-0')  # largeur fixe
                            with ui.column().classes('flex-1'):
                                ui.label(product["name"]).classes('text-xl font-semibold break-words')

                                if product.get('allow_reviews', False) and FILTER_PRODUCT_REVIEWS_ENABLED:
                                    avg = ratings_cache[product["id"]]
                                    with ui.row().classes('items-center gap-1 mt-1 rating-row'):
                                        if avg or avg == 0:
                                            for i in range(1, 6):
                                                ui.icon('star' if i <= round(avg) else 'star_border').classes('text-yellow-500 text-sm')
                                            ui.label(f"({reviews_cache[product['id']]})").classes('text-gray-500 text-xs ml-1')
                                        else:
                                            ui.label("Aucune note").classes('text-gray-400 text-xs')

                                with ui.row().classes('items-center gap-2 mt-2'):
                                    if product.get('display_price', False) and FILTER_PRICE_DISPLAY_ENABLED:
                                        ui.label(price_txt).classes('price-chip')
                                    if product.get('ordonnance', False):
                                        ui.label(t("prescription", lang_cookie)).classes('ord-chip')

                        if DISPLAY_TAGS_ENABLED:
                            with ui.row().classes('flex-wrap gap-2 mt-3'):
                                display_tags = product['tags'][:3]
                                for tag in display_tags:
                                    ui.label(tag).classes('tag-bubble cursor-pointer').style(f'background-color: {get_tag_color(tag)}; color: white;').on('click', lambda e, t=tag: add_tag(t))
                                if len(product['tags']) > 3:
                                    ui.label(f'+{len(product["tags"]) - 3}').classes('text-gray-500 text-xs')

                    def add_and_register(user_id, pid):
                        if add_panier_item(user_id, pid, request):
                            update_interaction(user_id, pid, increment=5)

                    ui.button(t("add_panier", lang_cookie), on_click=lambda e, pid=product["id"]: add_and_register(user_id, pid)).classes('btn-cart w-full')

        # Pagination
        with pagination_container:
            if state.current_page > 0:
                ui.button(on_click=lambda: change_page(-1), icon='chevron_left').props('flat').classes('rounded-full')
            ui.label(f"{t('page', lang_cookie)}{state.current_page + 1} / {total_pages}").classes('text-gray-600 mt-2')
            if state.current_page < total_pages - 1:
                ui.button(on_click=lambda: change_page(1), icon='chevron_right').props('flat').classes('rounded-full')


    # === Liaisons ===
    # search.on_value_change(lambda _: reset_page())
    debounce_timer = None

    search.on_value_change(lambda _: (search_spinner.classes(remove="hidden"), debounced_refresh()))

    def debounced_refresh():
        nonlocal debounce_timer
        if debounce_timer:
            debounce_timer.cancel()
        debounce_timer = ui.timer(0.3, lambda: (reset_page(), search_spinner.classes(add="hidden")), once=True)


    # === Appel initial ===
    refresh_products()