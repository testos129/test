from nicegui import ui, app
from fastapi.responses import RedirectResponse
from datetime import datetime
from fastapi import Request

from app.components.navbar import navbar
from app.components.theme import apply_background
from app.services.auth import get_current_user, sessions
from app.services.reviews import get_average_rating, get_review_infos
from app.services.users import record_visit, add_panier_item, get_connection, get_user_from_id, get_user_info
from app.services.items import get_tag_color, get_product, get_min_price_for_product
from app.recommendations.recommendations import find_similar_products
from app.recommendations.user_product_matrix import update_interaction, update_with_page
from app.translations.translations import t

from app.services.file_io import load_json, load_yaml
functionalities_switch = load_yaml('components/functionalities_switch.yaml')
FILTER_PRODUCT_REVIEWS_ENABLED = functionalities_switch.get('FILTER_PRODUCT_REVIEWS_ENABLED', True)
FILTER_PRICE_DISPLAY_ENABLED = functionalities_switch.get('FILTER_PRICE_DISPLAY_ENABLED', True)
FILTER_RECOMMENDATIONS_ENABLED = functionalities_switch.get('FILTER_RECOMMENDATIONS_ENABLED', True)
FILTER_PRODUCT_COMMENTS_ENABLED = functionalities_switch.get('FILTER_PRODUCT_COMMENTS_ENABLED', True)
banwords_list = load_json('components/banwords.json')['banwords']


@ui.page('/product/{product_id}')
def product_detail(product_id: str, request: Request):

    """Page détaillée d'un produit : affiche les détails d'un produit, permet de voir et laisser des avis, et montre des produits similaires."""

    # === Setup initial ===

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    if not get_current_user():
        return RedirectResponse('/')

    token = app.storage.browser.get('token')
    user_id = sessions[token]

    user_info = get_user_info(user_id)
    if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):  # utilisateur non confirmé et non admin
        return RedirectResponse('/')

    page = f'/product/{product_id}'
    record_visit(user_id, page)
    update_with_page(user_id, page)

    apply_background()
    navbar(request)

    lang_cookie = request.cookies.get("language", "fr")
    distance_cookie = float(request.cookies.get("max_distance", "10"))

    # Récupération du produit
    product = get_product(int(product_id))
    if not product:
        ui.label(t("product_not_found", lang_cookie)).classes('text-red-500 text-xl fade-in')
        return

    # Fonction pour afficher les étoiles de notation
    def display_stars(selected_rating, on_select, clickable=True):

        with ui.row().classes('mt-1'):
            for i in range(1, 6):
                icon = ui.icon('star' if i <= selected_rating else 'star_border') \
                    .classes('text-yellow-500 text-2xl cursor-pointer' if clickable else 'text-yellow-500 text-2xl')
                if clickable:
                    icon.on('click', lambda e, rating=i: on_select(rating))

    # Bouton retour home
    with ui.row().classes('w-full p-4 sticky top-0 left-0 z-50 bg-transparent'):
        ui.button(t("return_home", lang_cookie), on_click=lambda: ui.navigate.to('/home')) \
            .props('unelevated').classes('btn-back shadow-lg')


    # === Layout principal ===
    with ui.row().classes('w-full p-6 gap-x-6 items-start fade-in flex-col lg:flex-row'):


        # === Card produit principal ===
        with ui.column().classes('flex-[2] min-w-[300px]'):
            with ui.card().classes('main-product-card w-full').style("background-color: #F8FFFE"):  # F2FFFC
            
                # === Nom et rating ===
                with ui.column().classes('items-center text-center mb-4'):
                    ui.label(product["name"]).classes('text-3xl font-bold mb-2 text-center')
                    
                    if product.get('allow_reviews', False) and FILTER_PRODUCT_REVIEWS_ENABLED:  # Switch de functionnalité pour désactiver le check d'autorisation des reviews
                        avg = get_average_rating(product["id"])
                        if avg or avg == 0:
                            with ui.row().classes('justify-center items-center gap-3'):
                                for i in range(1, 6):
                                    ui.icon('star' if i <= round(avg) else 'star_border') \
                                        .classes('text-yellow-500 text-2xl')

                # === Image du produit ===
                ui.image('/' + product["image"]).props('fit=contain').classes(
                    'w-full max-h-80 object-contain rounded-xl shadow mb-4'
                ).style("background-color: #FFFFFF")  #F8FFFE

                # === Prix + ordonnance ===
                with ui.row().classes('items-center justify-center gap-4 mb-0'):
                    min_product_price = get_min_price_for_product(product['id'])
                    if min_product_price:
                        if product.get('display_price', False) and FILTER_PRICE_DISPLAY_ENABLED:  # Switch de functionnalité pour désactiver l'affichage du prix
                            with ui.row().classes('items-center justify-center mb-4'):
                                ui.label(t("price_from", lang_cookie)).classes('text-lg font-semibold')
                                ui.label(f"{min_product_price['price']:.2f} €").classes('price-chip')
                    else:
                        ui.label(t("not_available", lang_cookie)).classes('text-lg font-semibold text-gray-500')

                    if product.get('ordonnance', False):
                        ui.label(t("prescription", lang_cookie)).classes(
                            'bg-red-500 text-white text-xs font-semibold px-3 py-1 rounded-full'
                        )

                # === Description du produit ===
                ui.label(product["description"]).classes(
                    'text-base text-gray-700 text-center max-w-2xl mx-auto mt-2'
                )

                # === Tags du produit 
                with ui.row().classes('flex-wrap justify-center gap-2 mt-4'):
                    for tag in product['tags'][:5]:
                        ui.label(tag).classes('tag rounded-full px-3 py-1 text-sm text-white shadow') \
                            .style(f'background-color: {get_tag_color(tag)}')
                    if len(product['tags']) > 5:
                        ui.label('...').classes('text-gray-500 text-xs')

                # === Boutons d’action ===
                with ui.row().classes('mt-6 gap-3 justify-center'):
                    # Check disponibilité
                    ui.button(t("see_availabilities", lang_cookie),
                            on_click=lambda pid=product_id: ui.navigate.to(f'/product/{pid}/map')).classes('btn-secondary')
                    
                    # Ajout au panier
                    def add_and_register(user_id, pid):
                        if add_panier_item(user_id, pid, request):
                            update_interaction(user_id, pid, increment=5)

                    ui.button(t("add_panier", lang_cookie),
                            on_click=lambda pid=product_id: add_and_register(user_id, pid)).classes('btn-cart')


            # === Ecriture d'un commentaire et notation ===
            if product.get('allow_reviews', False) and user_info['allow_comments'] and FILTER_PRODUCT_REVIEWS_ENABLED:  # Switch de functionnalité pour désactiver le check d'autorisation des reviews
                current_rating = 0

                def set_rating(r):

                    """Met à jour la note actuelle de l'utilisateur et rafraîchit l'affichage des étoiles avec l'option d'envoyer un avis."""

                    nonlocal current_rating
                    current_rating = r
                    rating_container.clear()
                    with rating_container:
                        display_stars(current_rating, set_rating, clickable=True)
                        ui.button(t("send_review", lang_cookie), on_click=submit_review).classes("btn-edit mt-2")

                rating_container = ui.column().classes("card mt-8 w-full p-4 bg-gray-50 rounded-lg")
                with rating_container:
                    ui.label(t("give_review", lang_cookie)).classes("font-semibold mb-2")
                    display_stars(current_rating, set_rating, clickable=True)
                
                if FILTER_PRODUCT_COMMENTS_ENABLED:   # Switch de functionnalité pour désactiver la possibilité d'écrire un commentaire
                    comment_input = ui.textarea(t("comment", lang_cookie)).classes('w-full mt-4 rounded-lg')
                else:
                    comment_input = None


        # === Card espace commentaires ===
        if product.get('allow_reviews', False) and FILTER_PRODUCT_REVIEWS_ENABLED:  # Switch de functionnalité pour désactiver le check d'autorisation des reviews
            with ui.column().classes('flex-[1.5] min-w-[250px]'):
                with ui.card().classes('main-product-card mx-auto').style("background-color: #F0FBFF"):  #E0F7FF
                    reviews_container = ui.column().classes("mt-6 w-full")


                    def start_edit(review_id: int):

                        """Passe un avis en mode édition."""

                        with get_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE reviews SET editing = 1 WHERE id = ?", (review_id,))
                            conn.commit()
                        update_reviews_display()


                    def cancel_edit(review_id: int):

                        """Annule l'édition d'un avis."""

                        with get_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE reviews SET editing = 0 WHERE id = ?", (review_id,))
                            conn.commit()
                        update_reviews_display()


                    def save_edit(review_id: int, new_comment: str | None, new_rating: int | None):

                        """Sauvegarde les modifications apportées à un avis."""

                        for banword in banwords_list:
                            if new_comment and banword in new_comment:
                                ui.notify(t("banword", lang_cookie), color="negative")
                                return

                        with get_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                """UPDATE reviews
                                SET comment = ?, rating = ?, modified = 1, editing = 0
                                WHERE id = ?""",
                                (new_comment if new_comment else "", int(new_rating) if new_rating is not None else 0, review_id),
                            )
                            conn.commit()
                        ui.notify(t("comment_modified", lang_cookie), color="positive")
                        update_reviews_display()


                    def update_reviews_display():

                        """Vide et reconstruit l'affichage des avis depuis SQLite."""

                        reviews_container.clear()

                        with reviews_container:
                            with get_connection() as conn:
                                cursor = conn.cursor()
                                cursor.execute(
                                    """SELECT id, user_id, rating, comment, date, modified, editing
                                    FROM reviews WHERE product_id = ?
                                    ORDER BY date DESC""", (product_id,)
                                )
                                product_reviews = cursor.fetchall()

                            if not product_reviews:
                                ui.label(t("no_comments", lang_cookie)).classes("text-gray-500 italic")
                                return

                            ui.label(f"{t('num_reviews', lang_cookie)} ({len(product_reviews)})").classes("text-xl font-bold mb-3")

                            for row in product_reviews:
                                review = {
                                    "id": row[0],
                                    "user_id": row[1],
                                    "user": get_user_from_id(row[1]),
                                    "rating": row[2],
                                    "comment": row[3],
                                    "date": row[4],
                                    "modified": bool(row[5]),
                                    "editing": bool(row[6]),
                                }

                                # Card par avis
                                with ui.card().classes("mb-3 p-4 w-full rounded-xl shadow").style("background-color: #FFFFFF"):  #F0FBFF
                                    if not review["editing"]:
                                        with ui.row().classes("items-center justify-between"):
                                            display_stars(review["rating"], lambda _: None, clickable=False)
                                            ui.label(review["user"]).classes("text-base font-semibold ml-2")
                                            ui.label(review["date"]).classes("text-sm text-gray-600 ml-2")
                                            if review["modified"]:
                                                ui.label(t("modified", lang_cookie)).classes("text-xs text-gray-400 italic")

                                    # Mode édition
                                    if review["editing"]:
                                        if FILTER_PRODUCT_COMMENTS_ENABLED:   # Switch de functionnalité pour désactiver la possibilité d'écrire un commentaire
                                            edit_input = ui.textarea(value=review["comment"]).classes("w-full mb-2")
                                        else:
                                            edit_input = None
                                        edit_rating = {"value": review["rating"]}
                                        rating_container_inline = ui.row().classes("mb-2")

                                        def set_edit_rating(val, rc=rating_container_inline, er=edit_rating):

                                            er["value"] = int(val)
                                            rc.clear()
                                            with rc:
                                                display_stars(er["value"], set_edit_rating, clickable=True)

                                        with rating_container_inline:
                                            display_stars(edit_rating["value"], set_edit_rating, clickable=True)

                                        with ui.row().classes("gap-2 mt-2"):
                                            ui.button(t("validate", lang_cookie),
                                                on_click=lambda e, r=review, inp=edit_input, er=edit_rating:
                                                    save_edit(r["id"], inp.value if inp else None, er["value"])
                                            ).classes("btn-edit")
                                            ui.button(t("cancel", lang_cookie),
                                                on_click=lambda e, r=review: cancel_edit(r["id"])
                                            ).classes("btn-delete")

                                    # Affichage normal
                                    else:
                                        if FILTER_PRODUCT_COMMENTS_ENABLED:   # Switch de functionnalité pour désactiver la possibilité d'écrire un commentaire
                                            ui.label(review["comment"]).classes("text-gray-700 mt-2")
                                        if review["user_id"] == get_current_user() and user_info['allow_comments']:
                                            with ui.row().classes("gap-2 mt-2"):
                                                ui.button(t("modify", lang_cookie), on_click=lambda e, r=review: start_edit(r["id"])) \
                                                    .props("outline").classes("btn-edit")
                                                ui.button(t("delete_2", lang_cookie), on_click=lambda e, r=review: delete_review(r["id"])) \
                                                    .props("outline").classes("btn-delete")
                                        
                                        # Permission admin : supprimer les reviews des utilisateurs
                                        elif user_info.get('is_admin', False):
                                            ui.button(t("delete_2", lang_cookie), on_click=lambda e, r=review: delete_review(r["id"])) \
                                                    .props("outline").classes("btn-delete")


                    def submit_review():

                        """Enregistre ou met à jour l'avis d'un utilisateur connecté pour un produit donné dans la base de données."""

                        user_id = get_current_user()
                        if not user_id:
                            ui.notify(t("connected_to_review", lang_cookie), color="negative")
                            return
                        
                        with get_connection() as conn:
                            cursor = conn.cursor()

                            # Vérifie si l'utilisateur a déjà commenté ce produit
                            cursor.execute("SELECT id FROM reviews WHERE product_id = ? AND user_id = ?",
                                        (product_id, user_id))
                            existing_review = cursor.fetchone()

                            for banword in banwords_list:
                                if comment_input and banword in comment_input.value:
                                    ui.notify(t("banword", lang_cookie), color="negative")
                                    return

                            if existing_review:
                                cursor.execute("""UPDATE reviews
                                                SET rating = ?, comment = ?, modified = 1
                                                WHERE id = ?""",
                                            (current_rating, comment_input.value if comment_input else "", existing_review[0]))
                                ui.notify(t("review_modified", lang_cookie), color="positive")

                            else:
                                # Création
                                cursor.execute("""INSERT INTO reviews
                                                (product_id, user_id, rating, comment, date, modified, editing)
                                                VALUES (?, ?, ?, ?, ?, 0, 0)""",
                                            (product_id, user_id, current_rating,
                                                comment_input.value if comment_input else "", datetime.now().strftime("%Y-%m-%d %H:%M")))
                                ui.notify(t("review_saved", lang_cookie), color="positive")
                            conn.commit()
                        
                        # Réinitialise le champ de saisie et recharge l'affichage
                        if comment_input:
                            comment_input.set_value("")
                        update_reviews_display()


                    def delete_review(review_id: int):

                        """
                        Supprime un avis.
                        Si 'review_id' est fourni, on tente de supprimer exactement cet avis (vérifie l'auteur).
                        Sinon on supprime l'avis de l'utilisateur courant (fallback).
                        """

                        user_id = get_current_user()
                        if not user_id:
                            ui.notify(t("connected_to_review", lang_cookie), color="negative")
                            return
                        
                        with get_connection() as conn:
                            cursor = conn.cursor()

                            # Vérifier que l'utilisateur est bien l'auteur
                            review_info = get_review_infos(review_id)
                            if review_info['user_id'] != user_id  and not user_info.get('is_admin', False):
                                ui.notify(t("delete_other_reviews", lang_cookie), color="negative")
                                return
                            
                            cursor.execute("""DELETE FROM reviews
                                            WHERE product_id = ? AND user_id = ? AND comment = ? AND rating = ?""",
                                        (product_id, review_info["user_id"],
                                            review_info["comment"], review_info["rating"]))
                            conn.commit()
                        ui.notify(t("review_deleted", lang_cookie), color="positive")
                        update_reviews_display()

                    update_reviews_display()


        # === Colonne Produits similaires ===
        if product.get('display_recommendations', False) and FILTER_RECOMMENDATIONS_ENABLED:  # Switch de functionnalité pour désactiver les recommandations
            with ui.column().classes('flex-[0.75] min-w-[200px] lg:ml-8'):
                with ui.card().classes('main-product-card w-full fade-in max-h-[80vh] overflow-y-auto').style("background-color: #EDE9FE"):
                    ui.label(t("similar_products", lang_cookie)).classes('text-xl font-bold mb-4')

                    similar_products = find_similar_products(product['id'], min_common_tags=2)
                    if similar_products:
                        for sp in similar_products[:3]:
                            with ui.card().classes(
                                'mb-4 overflow-hidden cursor-pointer rounded-xl shadow hover:shadow-lg transition-all'
                            ).style("background-color: #F5F3FF") as card:
                                ui.image('/' + sp["image"]).props('fit=contain').classes(
                                    'w-full max-h-40 object-contain rounded-t-xl bg-transparent'
                                )

                                with ui.column().classes('p-3 items-center text-center'):
                                    ui.label(sp["name"]).classes('font-semibold truncate')
                                    if sp.get('allow_reviews', False) and FILTER_PRODUCT_REVIEWS_ENABLED:  # Switch de functionnalité pour désactiver le check d'autorisation des reviews
                                        avg = get_average_rating(sp["id"])
                                        if avg or avg == 0:
                                            with ui.row().classes("justify-center mt-1"):
                                                for i in range(1, 6):
                                                    ui.icon('star' if i <= round(avg) else 'star_border') \
                                                        .classes('text-yellow-500 text-sm')
                                                    
                            card.on('click', lambda e, pid=sp["id"]: ui.navigate.to(f'/product/{pid}'))
                    else:
                        ui.label(t("no_reco_product", lang_cookie)).classes('text-gray-500 italic')