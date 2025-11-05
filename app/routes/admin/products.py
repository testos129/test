from nicegui import ui, app
from fastapi.responses import RedirectResponse
import os
from pathlib import Path
from fastapi import Request

from services.auth import get_current_user, sessions
from components.navbar import navbar
from components.theme import apply_background
from services.users import get_user_info, get_connection
from services.items import delete_product
from translations.translations import t

IMAGES_DIR = Path("data/images")
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


@ui.page('/admin/products')
def admin_products(request: Request):

    """Page de gestion des produits pour les administrateurs."""

    # === Setup initial ===

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    if not get_current_user():
        return RedirectResponse('/')

    token = app.storage.browser.get('token')
    user_id = sessions[token]
    
    # Vérification des droits admin
    user_info = get_user_info(user_id)
    if not user_info.get('is_admin', False):
        return RedirectResponse('/home')
    
    apply_background()
    navbar(request)

    lang_cookie = request.cookies.get("language", "fr")
    distance_cookie = float(request.cookies.get("max_distance", "10"))

    state = {
        "page": 0,
        "search": "",
        "selected_product": None,
    }

    # Bouton retour
    with ui.row().classes('w-full p-4 sticky top-0 left-0 z-50 bg-transparent justify-start'):
        ui.button('⬅', on_click=lambda: ui.run_javascript('window.history.back()')) \
            .props('unelevated') \
            .classes('btn-back shadow-lg')


    # === Layout principal ===
    with ui.column().classes('items-center w-full max-w-6xl mx-auto p-8 gap-8'):
        
        # Titre
        ui.label(t("handle_products", lang_cookie)).classes('text-4xl font-extrabold text-center mb-6')

        with ui.column().classes('w-full gap-6 items-start flex-col lg:flex-row'):

            # Colonne gauche : liste + recherche
            with ui.column().classes('flex-1 min-w-[280px] max-w-[500px] gap-4 order-2 lg:order-1'):
                ui.label(t("products_list", lang_cookie)).classes('text-xl font-semibold mb-2')

                search_input = ui.input(placeholder=t("product_search", lang_cookie)) \
                    .props('outlined dense clearable').classes('w-full')
                
                ui.button(t("add", lang_cookie), on_click=lambda: manage_product("add")).props("flat").classes(
                        "bg-green-500 text-white px-4 py-2 rounded-lg hover:bg-green-600 ml-2"
                    )

                products_container = ui.column().classes('w-full gap-3')
                pagination_row = ui.row().classes('justify-between w-full mt-2')

            # Colonne droite : formulaire d’édition
            form_container = ui.card().classes(
                'flex-2 min-w-[400px] lg:min-w-[500px] p-6 bg-white shadow-md rounded-xl h-fit w-full order-1 lg:order-2'
            )


    # === Fonctions ===
    def load_products():

        """Charge les produits depuis la base de données en fonction de l'état actuel (page, recherche)."""

        products_container.clear()
        pagination_row.clear()

        with get_connection() as conn:
            cur = conn.cursor()
            query = """
                SELECT id, name, provider, image, description, reference, category, age_group,
                       allow_reviews, display_price, allow_order, display_recommendations, ordonnance
                FROM products
                WHERE name LIKE ? OR reference LIKE ? OR category LIKE ?
                LIMIT 5 OFFSET ?
            """
            cur.execute(
                query,
                (
                    f"%{state['search']}%",
                    f"%{state['search']}%",
                    f"%{state['search']}%",
                    state["page"] * 5
                )
            )
            products = cur.fetchall()

        for product in products:
            pid, name, provider, image, description, reference, category, age_group, allow_reviews, display_price, allow_order, display_recommendations, ordonnance = product
            with products_container:
                with ui.card().classes(
                    'w-full p-4 cursor-pointer hover:shadow-lg rounded-lg bg-white transition-all duration-200 hover:scale-[1.01]'
                ).on('click', lambda e, pid=pid: manage_product("edit", pid)):
                    ui.label(f"{name}").classes('font-semibold truncate')
                    ui.label(
                        f"{t('category', lang_cookie)}{category} | "
                        f"{t('provider', lang_cookie)}{provider}"
                    ).classes('text-sm text-gray-600')

        # Pagination
        with pagination_row:
            if state["page"] > 0:
                ui.button(icon='chevron_left', on_click=lambda: change_page(-1)).classes('bg-gray-200 rounded px-3')
            ui.label(f"{t('page', lang_cookie)}{state['page']+1}")
            if len(products) == 5:
                ui.button(icon='chevron_right', on_click=lambda: change_page(1)).classes('bg-gray-200 rounded px-3')


    def change_page(delta: int):

        state["page"] += delta
        load_products()


    def manage_product(mode: str = "add", product_id: int = None):

        """
        Formulaire d'ajout/édition d'un produit.
        mode: "add" ou "edit"
        """

        state['selected_product'] = product_id if mode == "edit" else None
        form_container.clear()

        product = None
        components, tags = [], []

        # Récupération des variables produit
        if mode == "edit":
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, name, provider, image, description, reference, category, age_group,
                        allow_reviews, display_price, allow_order, display_recommendations, ordonnance
                    FROM products WHERE id = ?
                """, (product_id,))
                product = cur.fetchone()

                if not product:
                    with form_container:
                        ui.label(t("product_not_found_2", lang_cookie)).classes("text-red-500")
                    return

                cur.execute("SELECT id, component FROM product_components WHERE product_id = ?", (product_id,))
                components = cur.fetchall()

                cur.execute("SELECT id, tag FROM product_tags WHERE product_id = ?", (product_id,))
                tags = cur.fetchall()

        if product:
            pid, pname, pprovider, pimage, pdesc, pref, pcat, page, arev, dprice, aorder, dreco, ordon = product
        else:
            pid, pname, pprovider, pimage, pdesc, pref, pcat, page, arev, dprice, aorder, dreco, ordon = \
                (None, "", "", None, "", "", "", "", 0, 0, 0, 0, 0)

        # Construction du formulaire
        with form_container:
            title = t("add_product", lang_cookie) if mode == "add" else f"{t('edit_product', lang_cookie)}{pname}"
            ui.label(title).classes('text-2xl font-bold mb-4')

            name_input = ui.input(t("product_name", lang_cookie), value=pname).classes("w-full")
            if mode == "edit":
                name_input.props("readonly")

            provider_input = ui.input(t("provider_2", lang_cookie), value=pprovider).classes("w-full")
            description_input = ui.textarea(t("description", lang_cookie), value=pdesc).classes("w-full")
            reference_input = ui.input(t("reference", lang_cookie), value=pref).classes("w-full")
            category_input = ui.input(t("category_2", lang_cookie), value=pcat).classes("w-full")
            age_group_input = ui.input(t("age_group", lang_cookie), value=page).classes("w-full")

            allow_reviews = ui.checkbox(t("allow_review", lang_cookie), value=bool(arev))
            display_price = ui.checkbox(t("display_price", lang_cookie), value=bool(dprice))
            allow_order = ui.checkbox(t("allow_order", lang_cookie), value=bool(aorder))
            display_reco = ui.checkbox(t("display_reco", lang_cookie), value=bool(dreco))
            ordonnance = ui.checkbox(t("prescription_mandatory", lang_cookie), value=bool(ordon))

            # === Gestion image ===
            uploaded_image_path = {"value": pimage}

            if pimage and os.path.exists(pimage):
                ui.image(pimage).classes("w-40 h-40 object-contain mb-2")

            ui.label(t("product_image", lang_cookie)).classes("font-semibold mt-4")

            def handle_upload(e):

                """Gère le téléchargement et l'enregistrement de l'image."""

                file = e.content
                filename = f"{name_input.value}.webp" if name_input.value else e.name
                if not filename.endswith(".webp"):
                    ui.notify(t("non_valid_image_format", lang_cookie), color="negative")
                    return

                save_path = IMAGES_DIR / filename
                with open(save_path, "wb") as f:
                    f.write(file.read())

                uploaded_image_path["value"] = str(save_path)
                ui.notify(t("image_saved", lang_cookie), color="positive")

            ui.upload(on_upload=handle_upload, auto_upload=True, max_file_size=5_000_000) \
                .props('accept=".webp"') \
                .classes("border p-4 rounded-lg w-full")

            # === Sections Composants ===
            if mode == "edit":
                ui.label(t("components", lang_cookie)).classes("text-lg font-semibold mt-6 mb-2")
                components_container = ui.column().classes("gap-2")

                def load_components():

                    """Charge les composants associés au produit."""

                    components_container.clear()
                    with get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT id, component FROM product_components WHERE product_id = ?", (pid,))
                        comps = cur.fetchall()
                    for cid, cname in comps:
                        with components_container:
                            with ui.row().classes("items-center justify-between w-full"):
                                ui.label(cname).classes("flex-1")
                                ui.button("❌", on_click=lambda e, cid=cid: delete_component(cid)) \
                                .classes("bg-red-500 text-white px-2 py-1 rounded")

                def add_component():

                    """Ajoute un nouveau composant au produit."""

                    def save_component():
                        if comp_input.value.strip():
                            with get_connection() as conn:
                                cur = conn.cursor()
                                cur.execute("INSERT INTO product_components (product_id, component) VALUES (?, ?)", (pid, comp_input.value.strip()))
                                conn.commit()
                            ui.notify(t("component_added", lang_cookie), color="positive")
                            dialog.close()
                            load_components()

                    dialog = ui.dialog()
                    with dialog, ui.card().classes("p-6"):
                        ui.label(t("add_component", lang_cookie)).classes("font-semibold mb-2")
                        comp_input = ui.input(t("component_name", lang_cookie)).classes("w-full")
                        ui.button(t("save", lang_cookie), on_click=save_component).classes("bg-blue-500 text-white mt-4")
                    dialog.open()

                def delete_component(cid: int):

                    """Supprime un composant du produit."""

                    with get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute("DELETE FROM product_components WHERE id = ?", (cid,))
                        conn.commit()
                    ui.notify(t("component_deleted", lang_cookie), color="warning")
                    load_components()

                ui.button(t("add_component", lang_cookie), on_click=add_component).classes("bg-green-500 text-white px-3 py-1 rounded")
                if pid:
                    load_components()

                # === Section Tags ===
                ui.label(t("tags", lang_cookie)).classes("text-lg font-semibold mt-6 mb-2")
                tags_container = ui.column().classes("gap-2")

                def load_tags():

                    """Charge les tags associés au produit."""

                    tags_container.clear()
                    with get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT id, tag FROM product_tags WHERE product_id = ?", (pid,))
                        ts = cur.fetchall()
                    for tid, tname in ts:
                        with tags_container:
                            with ui.row().classes("items-center justify-between w-full"):
                                ui.label(tname).classes("flex-1")
                                ui.button("❌", on_click=lambda e, tid=tid: delete_tag(tid)) \
                                .classes("bg-red-500 text-white px-2 py-1 rounded")

                def add_tag():

                    """Ajoute un nouveau tag au produit."""

                    def save_tag():
                        if tag_input.value.strip():
                            with get_connection() as conn:
                                cur = conn.cursor()
                                cur.execute("INSERT INTO product_tags (product_id, tag) VALUES (?, ?)", (pid, tag_input.value.strip()))
                                conn.commit()
                            ui.notify(t("tag_added", lang_cookie), color="positive")
                            dialog.close()
                            load_tags()

                    dialog = ui.dialog()
                    with dialog, ui.card().classes("p-6"):
                        ui.label(t("add_tag", lang_cookie)).classes("font-semibold mb-2")
                        tag_input = ui.input(t("tag_name", lang_cookie)).classes("w-full")
                        ui.button(t("save", lang_cookie), on_click=save_tag).classes("bg-blue-500 text-white mt-4")
                    dialog.open()

                def delete_tag(tid: int):

                    """Supprime un tag du produit."""

                    with get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute("DELETE FROM product_tags WHERE id = ?", (tid,))
                        conn.commit()
                    ui.notify(t("tag_deleted", lang_cookie), color="warning")
                    load_tags()

                ui.button(t("add_tag", lang_cookie), on_click=add_tag).classes("bg-green-500 text-white px-3 py-1 rounded")
                if pid:
                    load_tags()

            # === Boutons Save / Delete ===
            def save():

                """Sauvegarde les modifications ou l'ajout d'un produit."""

                if mode == "add":
                    # Vérification des champs obligatoires
                    required_fields = {
                        "Nom du produit": name_input.value,
                        "Fournisseur": provider_input.value,
                        "Image": uploaded_image_path["value"],
                        "Description": description_input.value,
                        "Référence": reference_input.value,
                        "Catégorie": category_input.value,
                        "Groupe d'âge": age_group_input.value,
                    }

                    for label, value in required_fields.items():
                        if not value or str(value).strip() == "":
                            ui.notify(f"{t('field', lang_cookie)}{label}{t('mandatory', lang_cookie)}", color="negative")
                            return

                    with get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT id FROM products WHERE name = ?", (name_input.value,))
                        if cur.fetchone():
                            ui.notify(t("existing_product_name", lang_cookie), color="warning")
                            return

                        cur.execute("""
                            INSERT INTO products (
                                name, provider, image, description, reference, category, age_group,
                                allow_reviews, display_price, allow_order, display_recommendations, ordonnance
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            name_input.value,
                            provider_input.value,
                            uploaded_image_path["value"],
                            description_input.value,
                            reference_input.value,
                            category_input.value,
                            age_group_input.value,
                            int(allow_reviews.value),
                            int(display_price.value),
                            int(allow_order.value),
                            int(display_reco.value),
                            int(ordonnance.value),
                        ))
                        conn.commit()
                    ui.notify(t("product_added", lang_cookie), color="positive")

                else:  # mode edit
                    with get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute("""
                            UPDATE products
                            SET provider=?, image=?, description=?, reference=?, category=?, age_group=?,
                                allow_reviews=?, display_price=?, allow_order=?, display_recommendations=?, ordonnance=?
                            WHERE id=?
                        """, (
                            provider_input.value,
                            uploaded_image_path["value"],
                            description_input.value,
                            reference_input.value,
                            category_input.value,
                            age_group_input.value,
                            int(allow_reviews.value),
                            int(display_price.value),
                            int(allow_order.value),
                            int(display_reco.value),
                            int(ordonnance.value),
                            pid,
                        ))
                        conn.commit()
                    ui.notify(t("product_updated", lang_cookie), color="positive")

                load_products()
                if mode == "edit":
                    manage_product("edit", pid)

            with ui.row().classes("items-center mt-4 w-full"):

                ui.button(t("save_2", lang_cookie), on_click=save).props("flat").classes(
                    "bg-blue-500 text-white px-6 py-2 rounded-lg hover:bg-blue-600"
                )

                ui.space()

                # === Bouton Supprimer (mode édition) ===
                if mode == "edit":
                    delete_button = ui.button(t("delete_3", lang_cookie)).props("flat").classes(
                        "bg-red-500 text-white px-6 py-2 rounded-lg hover:bg-red-600"
                    )

                    def perform_delete():

                        """Effectue la suppression du produit après confirmation."""

                        if delete_product(pid):
                            if pimage and os.path.exists(pimage):
                                try:
                                    os.remove(pimage)
                                except Exception as e:
                                    print(f"{t('error_image_deletion', lang_cookie)}{e}")
                            ui.notify(t("product_deleted", lang_cookie), color="warning")
                            form_container.clear()
                            load_products()
                        else:
                            ui.notify(t("impossible_deletion_product", lang_cookie), color="negative")

                    def confirm_delete():

                        """Affiche une boîte de dialogue de confirmation avant la suppression."""

                        dialog = ui.dialog()
                        with dialog:
                            with ui.card().classes("p-6"):
                                ui.label(f"{t('deletion_confirmation', lang_cookie)}{pname}{t('?', lang_cookie)}").classes("text-lg font-semibold mb-4")
                                with ui.row().classes("justify-end gap-4"):
                                    ui.button(t("cancel", lang_cookie), on_click=dialog.close).props("flat").classes("bg-gray-200 text-gray-800")
                                    ui.button(t("delete", lang_cookie), on_click=lambda e=None: (perform_delete(), dialog.close())).props("flat").classes(
                                        "bg-red-500 text-white hover:bg-red-600"
                                    )
                        dialog.open()

                    delete_button.on('click', lambda e=None: confirm_delete())


    # === Events ===
    search_input.on_value_change(lambda e: (state.update({"search": e.value}), load_products()))


    # === Initialisation ===
    load_products()
