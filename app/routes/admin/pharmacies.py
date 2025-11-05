from nicegui import ui, app
from fastapi.responses import RedirectResponse
from fastapi import Request

from services.auth import get_current_user, sessions
from components.navbar import navbar
from components.theme import apply_background
from services.users import get_user_info, get_connection
from services.items import delete_pharmacy
from translations.translations import t


@ui.page('/admin/pharmacies')
def admin_pharmacies(request: Request):

    """Page de gestion des pharmacies pour les admins."""

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
        "selected_pharmacy": None,
    }

    # Bouton retour
    with ui.row().classes('w-full p-4 sticky top-0 left-0 z-50 bg-transparent justify-start'):
        ui.button('⬅', on_click=lambda: ui.run_javascript('window.history.back()')) \
            .props('unelevated') \
            .classes('btn-back shadow-lg')


    # === Layout principal ===
    with ui.column().classes('items-center w-full max-w-6xl mx-auto p-8 gap-8'):
        ui.label(t("handle_pharmacies", lang_cookie)).classes('text-4xl font-extrabold text-center mb-6')

        with ui.column().classes('w-full gap-6 items-start flex-col lg:flex-row'):

            # === Colonne gauche : liste ===
            with ui.column().classes('flex-1 min-w-[280px] max-w-[500px] gap-4 order-2 lg:order-1'):
                ui.label(t("pharmacies_list", lang_cookie)).classes('text-xl font-semibold mb-2')

                search_input = ui.input(placeholder=t("pharmacy_search", lang_cookie)) \
                    .props('outlined dense clearable').classes('w-full')
                
                ui.button(t("add", lang_cookie), on_click=lambda: pharmacy_form("add")).props("flat").classes(
                    "bg-green-500 text-white px-4 py-2 rounded-lg hover:bg-green-600 ml-2"
                )

                pharmacies_container = ui.column().classes('w-full gap-3')
                pagination_row = ui.row().classes('justify-between w-full mt-2')

            # === Colonne droite : formulaire d’édition ===
            form_container = ui.card().classes(
                'flex-2 min-w-[400px] lg:min-w-[500px] p-6 bg-white shadow-md rounded-xl h-fit w-full order-1 lg:order-2'
            )


    # === Fonctions ===
    def load_pharmacies():

        """Charge et affiche la liste des pharmacies avec pagination et recherche."""

        pharmacies_container.clear()
        pagination_row.clear()

        with get_connection() as conn:
            cur = conn.cursor()
            query = """
                SELECT id, name, address, phone_number, latitude, longitude
                FROM pharmacies
                WHERE name LIKE ? OR address LIKE ?
                LIMIT 5 OFFSET ?
            """
            cur.execute(
                query,
                (
                    f"%{state['search']}%",
                    f"%{state['search']}%",
                    state["page"] * 5
                )
            )
            pharmacies = cur.fetchall()

        for ph in pharmacies:
            pid, name, address, phone, lat, lon = ph
            with pharmacies_container:
                with ui.card().classes(
                    'w-full p-4 cursor-pointer hover:shadow-lg rounded-lg bg-white transition-all duration-200 hover:scale-[1.01]'
                ).on('click', lambda e, pid=pid: pharmacy_form("edit", pid)):
                    ui.label(f"{name}").classes('font-semibold truncate')
                    ui.label(f"{address or t('unknown_addr', lang_cookie)}").classes('text-sm text-gray-600')

        # Pagination
        with pagination_row:
            if state["page"] > 0:
                ui.button(icon='chevron_left', on_click=lambda: change_page(-1)).classes('bg-gray-200 rounded px-3')
            ui.label(f"{t('page', lang_cookie)}{state['page']+1}")
            if len(pharmacies) == 5:
                ui.button(icon='chevron_right', on_click=lambda: change_page(1)).classes('bg-gray-200 rounded px-3')

    def change_page(delta: int):

        state["page"] += delta
        load_pharmacies()

    
    def pharmacy_form(mode="add", pharmacy_id=None):

        """Formulaire d'ajout/édition d'une pharmacie"""

        state['selected_pharmacy'] = pharmacy_id if mode == "edit" else None
        form_container.clear()

        # Variables par défaut
        pid, pname, paddr, pphone, plat, plon = None, "", "", "", None, None

        if mode == "edit":
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, name, address, phone_number, latitude, longitude
                    FROM pharmacies WHERE id = ?
                """, (pharmacy_id,))
                pharmacy = cur.fetchone()

            if not pharmacy:
                with form_container:
                    ui.label(t("unknown_pharmacy", lang_cookie)).classes("text-red-500")
                return

            pid, pname, paddr, pphone, plat, plon = pharmacy

        # Construction du formulaire
        with form_container:
            ui.label(t("add_pharmacy", lang_cookie) if mode == "add" else f"{t('edit_pharmacy', lang_cookie)}{pname}").classes('text-2xl font-bold mb-4')

            name_input = ui.input(t("pharmacy_name", lang_cookie), value=pname).props("readonly" if mode == "edit" else "").classes("w-full")
            address_input = ui.input(t("pharmacy_addr", lang_cookie), value=paddr).classes("w-full")
            phone_input = ui.input(t("pharmacy_phone", lang_cookie), value=pphone).classes("w-full")
            latitude_input = ui.input(t("pharmacy_lat", lang_cookie), value=str(plat) if plat else "").classes("w-full")
            longitude_input = ui.input(t("pharmacy_long", lang_cookie), value=str(plon) if plon else "").classes("w-full")

            # === Sauvegarde ===
            def save_pharmacy():

                """Sauvegarde les modifications ou l'ajout d'une pharmacie."""

                nonlocal pid
                with get_connection() as conn:
                    cur = conn.cursor()
                    if mode == "add":

                        # Vérification des champs obligatoires
                        if not name_input.value.strip():
                            ui.notify(t("name_mandatory", lang_cookie), color="negative")
                            return
                        if not latitude_input.value.strip() or not longitude_input.value.strip():
                            ui.notify(t("lat_long_mandatory", lang_cookie), color="negative")
                            return
                        
                        # Vérifier doublon
                        cur.execute("SELECT id FROM pharmacies WHERE name = ?", (name_input.value,))
                        if cur.fetchone():
                            ui.notify(t("existing_pharmacy_name", lang_cookie), color="warning")
                            return

                        cur.execute("""
                            INSERT INTO pharmacies (name, address, phone_number, latitude, longitude)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            name_input.value,
                            address_input.value,
                            phone_input.value,
                            latitude_input.value or None,
                            longitude_input.value or None,
                        ))
                        pid = cur.lastrowid
                        conn.commit()

                        ui.notify(t("pharmacy_added", lang_cookie), color="positive")
                        # Recharge directement en mode edit
                        pharmacy_form("edit", pid)

                    else:  # mode edit
                        cur.execute("""
                            UPDATE pharmacies
                            SET address=?, phone_number=?, latitude=?, longitude=?
                            WHERE id=?
                        """, (
                            address_input.value,
                            phone_input.value,
                            latitude_input.value or None,
                            longitude_input.value or None,
                            pid,
                        ))
                        conn.commit()

                        ui.notify(t("pharmacy_updated", lang_cookie), color="positive")
                        load_pharmacies()
                        pharmacy_form("edit", pid)

            ui.button(t("save_2", lang_cookie), on_click=save_pharmacy).props("flat").classes(
                "bg-blue-500 text-white px-6 py-2 rounded-lg hover:bg-blue-600 mt-4"
            )

            # === Gestion des produits (mode edit) ===
            if mode == "edit":
                ui.separator()
                ui.label(t("available_products", lang_cookie)).classes("text-xl font-semibold mt-6")

                products_section = ui.column().classes("w-full gap-3")

                def load_pharmacy_products():

                    """Charge et affiche les produits associés à la pharmacie."""

                    products_section.clear()
                    with get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute("""
                            SELECT pp.id, p.name, pp.price, pp.qty
                            FROM pharmacy_products pp
                            JOIN products p ON p.id = pp.product_id
                            WHERE pp.pharmacy_id = ?
                        """, (pid,))
                        rows = cur.fetchall()

                    for row_id, prod_name, price, qty in rows:
                        with products_section:
                            with ui.row().classes("items-center gap-4 w-full"):
                                ui.label(f"{prod_name}").classes("flex-1 font-medium")
                                price_input = ui.input(t("price", lang_cookie), value=str(price)).classes("w-24")
                                qty_input = ui.input(t("qty", lang_cookie), value=str(qty)).classes("w-20")

                                def save_update(row_id=row_id, price_input=price_input, qty_input=qty_input):

                                    """Sauvegarde les modifications d'un produit."""

                                    try:
                                        with get_connection() as conn:
                                            cur = conn.cursor()
                                            cur.execute("""
                                                UPDATE pharmacy_products
                                                SET price=?, qty=?
                                                WHERE id=?
                                            """, (float(price_input.value), int(qty_input.value), row_id))
                                            conn.commit()
                                        ui.notify(t("product_updated", lang_cookie), color="positive")
                                    except Exception as e:
                                        print("Error update product:", e)
                                        ui.notify(t("update_error", lang_cookie), color="negative")

                                def delete_product_from_pharmacy(row_id=row_id):

                                    """Supprime un produit de la pharmacie."""

                                    try:
                                        with get_connection() as conn:
                                            cur = conn.cursor()
                                            cur.execute("DELETE FROM pharmacy_products WHERE id=?", (row_id,))
                                            conn.commit()
                                        ui.notify(t("product_removed", lang_cookie), color="warning")
                                        load_pharmacy_products()
                                    except Exception as e:
                                        print("Erreur deletion product:", e)
                                        ui.notify(t("deletion_error", lang_cookie), color="negative")

                                ui.button("💾", on_click=save_update).props("flat").classes(
                                    "bg-blue-500 text-white rounded px-3 py-1")
                                ui.button("🗑️", on_click=delete_product_from_pharmacy).props("flat").classes(
                                    "bg-red-500 text-white rounded px-3 py-1")

                load_pharmacy_products()

                # === Ajout d’un produit ===
                ui.separator()
                ui.label(t("add_product_2", lang_cookie)).classes("text-lg font-semibold mt-4")

                with ui.row().classes("items-center gap-3"):
                    product_select = ui.select(
                        {row[0]: row[1] for row in get_connection().cursor().execute("SELECT id, name FROM products").fetchall()},
                        label=t("product", lang_cookie)
                    ).classes("flex-1")
                    price_input_new = ui.input(t("price", lang_cookie)).classes("w-24")
                    qty_input_new = ui.input(t("qty", lang_cookie)).classes("w-20")

                    def add_product_to_pharmacy():

                        """Ajoute un produit à la pharmacie."""

                        if not product_select.value:
                            ui.notify(t("no_product_selected", lang_cookie), color="negative")
                            return
                        try:
                            with get_connection() as conn:
                                cur = conn.cursor()
                                cur.execute("""
                                    INSERT OR REPLACE INTO pharmacy_products (pharmacy_id, product_id, price, qty)
                                    VALUES (?, ?, ?, ?)
                                """, (pid, product_select.value, float(price_input_new.value or 0), int(qty_input_new.value or 0)))
                                conn.commit()
                            ui.notify(t("product_added_or_updated", lang_cookie), color="positive")
                            load_pharmacy_products()
                        except Exception as e:
                            print("Erreur ajout produit:", e)
                            ui.notify(t("add_error", lang_cookie), color="negative")

                    ui.button("Ajouter", on_click=add_product_to_pharmacy).classes("bg-green-500 text-white rounded px-4 py-2 mt-2")

                # === Suppression pharmacie ===
                def perform_delete():

                    """Supprime la pharmacie après confirmation."""

                    if delete_pharmacy(pid):
                        ui.notify(t("pharmacy_deleted", lang_cookie), color="warning")
                        form_container.clear()
                        load_pharmacies()
                    else:
                        ui.notify(t("error_pharmacy_deletion", lang_cookie), color="negative")

                delete_button = ui.button(t("delete_3", lang_cookie)).props("flat").classes(
                    "bg-red-500 text-white px-4 py-2 rounded-lg hover:bg-red-600 mt-4")

                def confirm_delete():

                    """Affiche une boîte de confirmation avant de supprimer la pharmacie."""

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
    search_input.on_value_change(lambda e: (state.update({"search": e.value}), load_pharmacies()))


    # === Initialisation ===
    load_pharmacies()