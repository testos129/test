from nicegui import ui, app
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi import Request
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import io

from services.auth import get_current_user
from services.users import get_user_info, get_last_order
from components.navbar import navbar
from components.footer import footer_bar
from components.theme import apply_background
from services.logging_setup import get_logger
from translations.translations import t


@app.get("/generate_last_order_pdf")
def generate_last_order_pdf(request: Request):

    """Génère un PDF récapitulatif de la dernière commande de l'utilisateur."""

    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for api generate order pdf: no valid token, ip: {host}")
        return RedirectResponse('/')

    user_info = get_user_info(user_id)
    lang_cookie = request.cookies.get("language", "fr")

    last_order = get_last_order(user_id)
    if not last_order:
        return RedirectResponse('/thanks')

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
    elements.append(Paragraph(f"{t('order_date', lang_cookie)}{last_order['date']}", styles["Normal"]))
    if last_order['address']:
        elements.append(Paragraph(f"{t('order_address', lang_cookie)}{last_order['address']}", styles["Normal"]))
        if last_order['address_details']:  # Seulement quand on a déjà l'adresse renseignée
            elements.append(Paragraph(f"{t('order_address_details', lang_cookie)}{last_order['address_details']}", styles["Normal"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"{t('delivery_fees', lang_cookie)}{last_order['delivery_cost']:.2f} €", styles["Normal"]))
    elements.append(Paragraph(f"{t('Total payé : ', lang_cookie)}{last_order['total']:.2f} €", styles["Normal"]))
    elements.append(Spacer(1, 20))

    # Tableau produits
    data = [["Produit", "Quantité", "Prix (€)"]]
    for item in last_order["items"]:
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

    logger = get_logger('nav')
    logger.info(f"Order pdf recap generated for order: {last_order['order_id']}", extra={"user_id": user_id})

    # Utilisation de StreamingResponse pour envoyer un flux mémoire
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename=commande.pdf"
        }
    )


@ui.page('/thanks')
def thanks(request: Request):

    """Page de remerciement après une commande réussie."""

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for page thanks: no valid token, ip: {host}")
        return RedirectResponse('/')
    
    logger = get_logger('nav')
    
    user_info = get_user_info(user_id)
    if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):  # utilisateur non confirmé et non admin
        logger.info("Access denied for page thanks: not confirmed", extra={"user_id": user_id})
        return RedirectResponse('/')
    
    apply_background()
    navbar(request)
    footer_bar(request)

    lang_cookie = request.cookies.get("language", "fr")    
    
    # === Contenu de la page ===

    with ui.column().classes('items-center w-full max-w-3xl mx-auto p-4 gap-4'):
        last_order = get_last_order(user_id)

        ui.label(t("thanks_order", lang_cookie)).classes('text-3xl font-bold text-center mt-4')
        ui.label(t("order_number", lang_cookie) + str(last_order['order_id'])).classes('text-xl font-bold text-center mt-4')
        ui.label(t("order_registered", lang_cookie)).classes('text-gray-700 text-center')

        ui.button(t("return_home_2", lang_cookie), on_click=lambda: ui.navigate.to('/home')) \
            .props('unelevated') \
            .classes('btn-return-home')

        ui.button(t("download_receipt", lang_cookie), on_click=lambda: ui.run_javascript("window.open('/generate_last_order_pdf', '_blank')")) \
            .props('unelevated') \
            .classes('btn-download-receipt')
