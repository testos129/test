from nicegui import ui, app
from fastapi.responses import RedirectResponse
from fastapi import Request
from datetime import datetime

from services.auth import get_current_user, sessions
from components.navbar import navbar
from components.theme import apply_background
from services.users import get_user_info, delete_user, get_connection
from translations.translations import t


@ui.page('/admin/users')
def admin_users(request: Request):

    """Page de gestion des utilisateurs pour les administrateurs."""

    # === Setup initial ===

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    if not get_current_user():
        return RedirectResponse('/')

    token = app.storage.browser.get('token')
    user_id = sessions[token]

    # user_id = get_current_user(request)
    # if not user_id:
    #     return RedirectResponse('/')
    
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
        "selected_user": None,
    }

    # Bouton retour
    with ui.row().classes('w-full p-4 sticky top-0 left-0 z-50 bg-transparent justify-start'):
        ui.button('⬅', on_click=lambda: ui.run_javascript('window.history.back()')) \
            .props('unelevated') \
            .classes('btn-back shadow-lg')

    # === Contenu de la page ===
    with ui.column().classes('items-center w-full max-w-6xl mx-auto p-8 gap-8'):
        
        # Titre
        ui.label(t("handle_users", lang_cookie)).classes(
            'text-4xl font-extrabold text-center mb-6'
        )

        with ui.column().classes('w-full gap-6 items-start flex-col lg:flex-row'):
            
            # Colonne gauche : Liste
            with ui.column().classes('flex-1 min-w-[280px] max-w-[500px] gap-4 order-2 lg:order-1'):
                ui.label(t("users_list", lang_cookie)).classes('text-xl font-semibold mb-2')

                search_input = ui.input(placeholder=t("user_search", lang_cookie)) \
                    .props('outlined dense clearable').classes('w-full')

                users_container = ui.column().classes('w-full gap-3')
                pagination_row = ui.row().classes('justify-between w-full mt-2')

            # Colonne droite : Formulaire d'édition
            form_container = ui.card().classes(
                'flex-2 min-w-[400px] lg:min-w-[500px] p-6 bg-white shadow-md rounded-xl h-fit w-full order-1 lg:order-2'
            )

    # === Fonctions ===
    def load_users():

        """Charge les utilisateurs selon la recherche et la pagination."""

        users_container.clear()
        pagination_row.clear()

        with get_connection() as conn:
            cur = conn.cursor()
            query = """
                SELECT id, username, email, is_delivery_person, is_admin, is_confirmed, allow_comments
                FROM users
                WHERE username LIKE ? 
                OR email LIKE ?
                OR (? LIKE '%admin%' AND is_admin = 1)
                OR (? LIKE '%livreur%' AND is_delivery_person = 1)
                OR (? LIKE '%confirmé%' AND is_confirmed = 1)
                LIMIT 5 OFFSET ?
            """
            cur.execute(
                query,
                (
                    f"%{state['search']}%",  # username
                    f"%{state['search']}%",  # email
                    state['search'],         # "admin"
                    state['search'],         # "livreur"
                    state['search'],         # "confirmé"
                    state["page"] * 5        # offset
                )
            )
            users = cur.fetchall()


        for user in users:
            uid, uname, uemail, is_del, is_admin, is_conf, allow_com = user
            with users_container:
                with ui.card().classes(
                    'w-full p-4 cursor-pointer hover:shadow-lg rounded-lg bg-white '
                    'transition-all duration-200 hover:scale-[1.01]'
                ).on('click', lambda e, uid=uid: edit_user(uid)):
                    ui.label(f"{uname} ({uemail})").classes('font-semibold truncate')
                    ui.label(
                        f"{t('admin', lang_cookie)}{'✔️' if is_admin else '❌'} | "
                        f"{t('delivery_person', lang_cookie)}{'✔️' if is_del else '❌'} | "
                        f"{t('confirmed', lang_cookie)}{'✔️' if is_conf else '❌'}"
                    ).classes('text-sm text-gray-600')

        # Pagination
        with pagination_row:
            if state["page"] > 0:
                ui.button(icon='chevron_left', on_click=lambda: change_page(-1)).classes('bg-gray-200 rounded px-3')
            ui.label(f"{t('page', lang_cookie)}{state['page']+1}")
            if len(users) == 5:
                ui.button(icon='chevron_right', on_click=lambda: change_page(1)).classes('bg-gray-200 rounded px-3')

    def change_page(delta: int):

        state["page"] += delta
        load_users()

    def edit_user(user_id: int):

        """Charge le formulaire d'édition pour un utilisateur donné."""

        state['selected_user'] = user_id
        form_container.clear()

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, username, email, is_delivery_person, is_admin, is_confirmed, allow_comments FROM users WHERE id = ?",
                (user_id,),
            )
            user = cur.fetchone()

            # Récupérer le wallet
            cur.execute("SELECT balance FROM wallets WHERE user_id = ?", (user_id,))
            wallet_row = cur.fetchone()
            wallet_balance = wallet_row[0] if wallet_row else 0.0

        if not user:
            with form_container:
                ui.label(t("user_not_found", lang_cookie)).classes("text-red-500")
            return

        uid, uname, uemail, is_del, is_admin, is_conf, allow_com = user

        with form_container:
            ui.label(f"{t('edit_user', lang_cookie)}{uname}").classes('text-2xl font-bold mb-4')

            ui.input(t("username", lang_cookie), value=uname).props("readonly").classes("w-full")
            email_input = ui.input(t("email", lang_cookie), value=uemail).classes("w-full")

            admin_checkbox = ui.checkbox(t("admin_2", lang_cookie), value=bool(is_admin))
            delivery_checkbox = ui.checkbox(t("delivery_person_2", lang_cookie), value=bool(is_del))
            confirmed_checkbox = ui.checkbox(t("confirmed_2", lang_cookie), value=bool(is_conf))
            allow_comments_checkbox = ui.checkbox(t("allow_comments", lang_cookie), value=bool(allow_com))

            wallet_input = ui.input(t("wallet_amount", lang_cookie), value=f"{wallet_balance:.2f}").classes("w-full").props("type=number step=1 min=0")

            def save():

                """Sauvegarde les modifications apportées à l'utilisateur."""

                try:
                    wallet_value = round(float(wallet_input.value), 2) 
                    if wallet_value < 0:
                        ui.notify(t("negative_wallet_amount", lang_cookie), color="negative")
                        return
                except ValueError:
                    ui.notify(t("invalid_wallet_amount", lang_cookie), color="negative")
                    return
                
                with get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        UPDATE users
                        SET email = ?, is_delivery_person = ?, is_admin = ?, is_confirmed = ?, allow_comments = ?
                        WHERE id = ?
                    """, (
                        email_input.value,
                        int(delivery_checkbox.value),
                        int(admin_checkbox.value),
                        int(confirmed_checkbox.value),
                        int(allow_comments_checkbox.value),
                        uid,
                    ))

                    wallet_update_amount = float(wallet_input.value) - wallet_balance

                    # Mettre à jour ou créer le wallet
                    cur.execute("SELECT id FROM wallets WHERE user_id = ?", (uid,))
                    if cur.fetchone():
                        cur.execute("UPDATE wallets SET balance = ? WHERE user_id = ?", (float(wallet_input.value), uid))
                    else:
                        cur.execute("INSERT INTO wallets (user_id, balance) VALUES (?, ?)", (uid, float(wallet_input.value)))

                    # Mettre à jour l'historique du wallet
                    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    cur.execute(
                        "INSERT INTO wallet_history (user_id, date, amount, description) VALUES (?, ?, ?, ?)",
                        (uid, today, wallet_update_amount, "admin_edit"),
                    )

                    conn.commit()

                ui.notify(t("user_updated", lang_cookie), color="positive")
                load_users()
                edit_user(uid)  # recharge le form avec valeurs actualisées

            # Boutons d'action
            with ui.row().classes("gap-4 mt-6"):
                ui.button(t("save_2", lang_cookie), on_click=save).props("flat").classes(
                    "bg-blue-500 text-white px-6 py-2 rounded-lg hover:bg-blue-600"
                )

                delete_button = ui.button(
                    t("delete_2", lang_cookie),
                ).props("flat").classes(
                    "bg-red-500 text-white px-4 py-2 rounded-lg hover:bg-red-600"
                )

                if is_admin:
                    delete_button.props("disabled")

                # Fonction de suppression
                def perform_delete():

                    """Effectue la suppression de l'utilisateur après confirmation."""
                    
                    if delete_user(uid):
                        ui.notify(t("user_deleted", lang_cookie), color="warning")
                        form_container.clear()
                        load_users()
                    else:
                        ui.notify(t("impossible_deletion_user", lang_cookie), color="negative")

                # Confirmation popup
                def confirm_delete():

                    """Affiche une boîte de dialogue de confirmation avant la suppression."""

                    # Création dynamique du dialog à l'intérieur du clic
                    dialog = ui.dialog()
                    with dialog:
                        with ui.card().classes("p-6"):
                            ui.label(f"{t('deletion_confirmation', lang_cookie)}{uname}{t('?', lang_cookie)}").classes("text-lg font-semibold mb-4")
                            with ui.row().classes("justify-end gap-4"):
                                ui.button(t("cancel", lang_cookie), on_click=dialog.close).props("flat").classes("bg-gray-200 text-gray-800")
                                ui.button(t("delete", lang_cookie), on_click=lambda e=None: (perform_delete(), dialog.close())).props("flat").classes(
                                    "bg-red-500 text-white hover:bg-red-600"
                                )
                    dialog.open()

                # Lier le bouton au popup
                delete_button.on('click', lambda e=None: confirm_delete())


    # === Events ===
    search_input.on_value_change(lambda e: (state.update({"search": e.value}), load_users()))


    # === Initialisation ===
    load_users()
