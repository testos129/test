from nicegui import ui, app
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi import Request
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import io

from components.theme import apply_background
from components.navbar import navbar
from services.auth import get_current_user, sessions
from services.users import get_user_info, update_user, get_visit_history, get_user_from_id, get_order_history, get_order_details
from security.passwords import hash_password
from translations.translations import t


@app.get("/generate_order_pdf")
def generate_order_pdf(order_id: int, request: Request):

    """Génère un PDF récapitulatif de la commande de l'utilisateur."""

    token = app.storage.browser.get('token')
    if not token or token not in sessions:
        return RedirectResponse('/')

    user_id = sessions[token]
    user_info = get_user_info(user_id)
    lang_cookie = request.cookies.get("language", "fr")

    order_details = get_order_details(order_id)

    # Création du PDF en mémoire
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(t("order_summary", lang_cookie), styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"{t('name', lang_cookie)}{user_info['username']}", styles["Normal"]))
    elements.append(Paragraph(f"{t('email_2', lang_cookie)}{user_info['email']}", styles["Normal"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"{t('order_date', lang_cookie)}{order_details['date']}", styles["Normal"]))
    elements.append(Paragraph(f"{t('delivery_fees', lang_cookie)}{order_details['delivery_cost']:.2f} €", styles["Normal"]))
    elements.append(Paragraph(f"{t('Total payé : ', lang_cookie)}{order_details['total']:.2f} €", styles["Normal"]))
    elements.append(Spacer(1, 20))

    # Tableau produits
    data = [["Produit", "Quantité", "Prix (€)"]]
    for item in order_details["items"]:
        data.append([item["name"], str(item["qty"]), f"{item['price']:.2f}"])

    table = Table(data, colWidths=[200, 100, 100])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
    ]))
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)

    # Utilisation de StreamingResponse pour envoyer un flux mémoire
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename=commande.pdf"
        }
    )


@ui.page('/profile')
def profile_page(request: Request):

    """Page de profil utilisateur avec possibilité de modifier l'email et le mot de passe, et affichage de l'historique des visites."""

    # === Setup initial ===

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    if not get_current_user():
        return RedirectResponse('/')
    
    token = app.storage.browser.get('token')
    user_id = sessions[token]
    
    user_info = get_user_info(user_id)
    if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):  # utilisateur non confirmé et non admin
        return RedirectResponse('/')
    
    apply_background()
    navbar(request)

    lang_cookie = request.cookies.get("language", "fr")
    distance_cookie = float(request.cookies.get("max_distance", "10"))

    # Bouton retour
    with ui.row().classes('w-full p-4 sticky top-0 left-0 z-50 bg-transparent'):
        ui.button('⬅', on_click=lambda: ui.run_javascript('window.history.back()')) \
            .props('unelevated') \
            .classes('btn-back shadow-lg')

    token = app.storage.browser.get('token')
    user_id = sessions[token]
    username = get_user_from_id(user_id)


    # === Edition du profil ===
    with ui.column().classes('items-center p-6 w-full max-w-2xl m-auto glass-card fade-in'):

        # === Affichage du nom et avatar ===
        with ui.row().classes('w-full items-center justify-between'):
            # Image de profil par défaut en se basant sur le nom d'utilisateur
            ui.image(f"https://ui-avatars.com/api/?name={username}&background=2e7d32&color=fff&size=128") \
                    .classes('rounded-full border-2 border-white shadow-md') \
                    .style('width:80px; height:80px; object-fit:cover;')
            
            ui.label(t("profil", lang_cookie)).classes('text-3xl font-bold mb-4 text-black')
        
        # === Reset de l'email ou mot de passe ===
        # user_info = get_user_info(user_id)
        if user_info:
            current_email = user_info['email']
            current_address = user_info['delivery_address']
        else:
            current_email = ""


        email = ui.input(t("email", lang_cookie), value=current_email).classes('w-full')
        # Mot de passe non prérempli pour ne pas exposer l'ancien
        password = ui.input(
            t("change_password", lang_cookie),
            password=True,
            password_toggle_button=True
        ).classes('w-full')
        address = ui.input(t("new_address", lang_cookie), value=current_address).classes('w-full')


        def save_changes():

            """Enregistre les modifications de l'email et/ou du mot de passe."""

            new_email = email.value.strip() or None
            new_password = password.value.strip() or None
            new_address = address.value or None

            if new_password:
                # Hash du nouveau mot de passe
                pwd_hash = hash_password(new_password)
                update_user(user_id, new_email, pwd_hash, new_address)
                ui.notify(t("update_info", lang_cookie), color='positive')
            else:
                update_user(user_id, new_email, None, new_address)
                ui.notify(t("update_info", lang_cookie), color='positive')


        ui.button(t("save_2", lang_cookie), on_click=save_changes).classes('btn-success mt-4')
    

    # === Affichage de l'historique des commandes ===
    orders = get_order_history(user_id)

    with ui.column().classes("items-center p-6 w-full max-w-3xl m-auto fade-in"):
        ui.label(t("order_history", lang_cookie)).classes(
            "text-3xl font-bold mb-6 text-black"
        )

        if not orders:
            ui.label(t("no_order", lang_cookie)).classes(
                "text-gray-500 italic"
            )
        else:
            for order_id, date, total, items in orders[:10]:  # Limite à 10 commandes récentes
                with ui.card().classes(
                    "relative w-full bg-white/90 shadow-lg rounded-2xl p-6 mb-4 border border-gray-200 hover:shadow-xl transition-all duration-300"
                ):
                    # Ligne du haut : numéro, date et bouton download à droite
                    with ui.row().classes("justify-between items-start mb-2 w-full"):
                        with ui.column().classes("gap-0"):
                            ui.label(f"{t('order_number', lang_cookie)} {order_id}").classes(
                                "text-lg font-semibold text-gray-800"
                            )
                            ui.label(f"{date}").classes(
                                "text-sm text-gray-500 italic"
                            )

                        # Bouton de téléchargement en haut à droite
                        ui.button(
                            on_click=lambda order_id=order_id: ui.run_javascript(
                                f"window.open('/generate_order_pdf?order_id={order_id}', '_blank')"
                            ),
                            icon='file_download'
                        ).props('unelevated round dense').classes('absolute top-3 right-3 text-gray-600 hover:text-green-600 transition')

                    # Contenu du corps
                    ui.label(f"{t('articles_list', lang_cookie)} {items}").classes(
                        "text-gray-700 mb-2"
                    )
                    ui.label(f"{t('total', lang_cookie)} {total:.2f} €").classes(
                        "font-bold text-green-600 text-lg"
                    )
                    

    # === Affichage de l'historique des visites ===
    history = get_visit_history(user_id)

    with ui.column().classes("items-center p-6 w-full max-w-2xl m-auto glass-card fade-in mt-6"):
        
        ui.label(t("visit_history", lang_cookie)).classes("text-2xl font-bold mb-4 text-black")
        if not history:
            ui.label(t("no_visit", lang_cookie)).classes("text-gray-200 italic")
        else:
             for page, info in sorted(history.items(), key=lambda x: x[1][1], reverse=True)[:20]:  # x[1][1] pour récupérer info puis count
                display_page, count = info
                ui.label(f"{display_page} : {count} {t('visits', lang_cookie) if count > 1 else t('visit', lang_cookie)}")  \
                    .classes("text-black bg-black/20 px-4 py-2 rounded-lg w-full text-center hover:bg-black/30 transition-all duration-300")