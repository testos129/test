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
from components.footer import footer_bar
from services.auth import get_current_user
from services.users import get_user_info, update_user, get_visit_history, get_order_history, get_order_details
from security.passwords import hash_password
from services.distance import distance_by_day
from services.settings import get_setting
from services.logging_setup import get_logger
from translations.translations import t

from services.file_io import load_yaml
functionalities_switch = load_yaml('components/functionalities_switch.yaml')
ENABLE_SET_DISTANCE_LIMIT = functionalities_switch.get('ENABLE_SET_DISTANCE_LIMIT', True)


@app.get("/generate_order_pdf")
def generate_order_pdf(order_id: int, request: Request):

    """Génère un PDF récapitulatif de la commande de l'utilisateur."""

    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for api generate order pdf: no valid token, ip: {host}")
        return RedirectResponse('/')

    user_info = get_user_info(user_id)
    lang_cookie = request.cookies.get("language", "fr")

    order_details = get_order_details(order_id)
    if order_details['user_id'] != user_id:
        logger = get_logger('nav')
        logger.warning(f"Unauthorized PDF access attempt for order {order_id}", extra={"user_id": user_id})
        return RedirectResponse('/')

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
    if order_details['address']:
        elements.append(Paragraph(f"{t('order_address', lang_cookie)}{order_details['address']}", styles["Normal"]))
        if order_details['address_details']:  # Seulement quand on a déjà l'adresse renseignée
            elements.append(Paragraph(f"{t('order_address_details', lang_cookie)}{order_details['address_details']}", styles["Normal"]))
    elements.append(Spacer(1, 12))
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

    logger = get_logger('nav')
    logger.info(f"Order pdf recap generated for order: {order_id}", extra={"user_id": user_id})

    # Utilisation de StreamingResponse pour envoyer un flux mémoire
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename=commande.pdf"
        }
    )


@ui.page('/profile')
def profile_page(request: Request, open_contact: bool = False):

    """Page de profil utilisateur avec possibilité de modifier l'email et le mot de passe, et affichage de l'historique des visites."""

    # === Setup initial ===

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for page profil: no valid token, ip: {host}")
        return RedirectResponse('/')
    
    logger = get_logger('nav')

    user_info = get_user_info(user_id)
    if not user_info.get('is_confirmed', False) and not user_info.get('is_admin', False):  # utilisateur non confirmé et non admin
        logger.info("Access denied for page profil: not confirmed", extra={"user_id": user_id})
        return RedirectResponse('/')
    
    apply_background()
    navbar(request)
    footer_bar(request)

    lang_cookie = request.cookies.get("language", "fr")
    distance_cookie = float(request.cookies.get("max_distance", distance_by_day()))

    # Bouton retour
    with ui.row().classes('w-full p-4 sticky top-0 left-0 z-50 bg-transparent'):
        ui.button(t("return_home", lang_cookie), on_click=lambda: ui.navigate.to('/home')) \
            .props('unelevated') \
            .classes('btn-back shadow-lg')

    # === Récupération des informations utilisateur ===
    current_email = user_info.get('email', '')
    current_phone = user_info.get('phone_number', '')

    # === Adresse principale ===
    current_main_street = user_info.get('main_address_street', '')
    current_main_city = user_info.get('main_address_city', '')
    current_main_postal_code = user_info.get('main_address_postal_code', '')
    current_main_details = user_info.get('main_address_details', '')

    # === Adresse secondaire ===
    current_secondary_street = user_info.get('secondary_address_street', '')
    current_secondary_city = user_info.get('secondary_address_city', '')
    current_secondary_postal_code = user_info.get('secondary_address_postal_code', '')
    current_secondary_details = user_info.get('secondary_address_details', '')

    # === Card principale ===
    with ui.card().classes('w-full max-w-3xl m-auto p-6 glass-card fade-in mt-6'):

        # === En-tête profil ===
        with ui.row().classes('w-full justify-center mt-2'):
            ui.label(t("profil", lang_cookie)).classes('text-3xl font-bold text-black text-center')


        # === Section 1 : Informations de base ===
        with ui.expansion(icon='home', text=t("basic_info", lang_cookie), value=False).classes('w-full bg-white/90 rounded-xl shadow-md mt-4'):

            # === Distance max ===
            if ENABLE_SET_DISTANCE_LIMIT:
                distance_input = ui.number("Distance maximale (km)", value=distance_cookie).props("outlined").classes("w-full mb-4")
            
            # === Numéro de téléphone ===
            phone_number = ui.input(t("phone_number", lang_cookie), value=current_phone).classes('w-full mt-2')
            
            # === Adresse principale ===
            ui.label(t("main_address", lang_cookie)).classes('text-lg mt-4')

            address = ui.input(t("new_address", lang_cookie), value=current_main_street).classes('w-full mt-2')
            with ui.row():
                city = ui.input(t("city", lang_cookie), value=current_main_city).classes('w-full mt-2')
                postal_code = ui.input(t("postal_code", lang_cookie), value=current_main_postal_code).classes('w-full mt-2')
            address_details = ui.input(t("address_details", lang_cookie), value=current_main_details).classes('w-full mt-2')

            # === Adresse secondaire (optionnelle) ===
            add_second_address = ui.checkbox(t("add_secondary_address", lang_cookie)).classes('mt-2')

            second_address_section = ui.column().classes('hidden')

            def toggle_second_address(e):

                if add_second_address.value:
                    second_address_section.classes(remove='hidden')
                else:
                    second_address_section.classes(add='hidden')

            add_second_address.on_value_change(toggle_second_address)

            with second_address_section:
                ui.label(t("secondary_address_option", lang_cookie)).classes('text-lg mt-2')
                second_address = ui.input(t("new_address", lang_cookie), value=current_secondary_street).classes('w-full mt-2')
                with ui.row():
                    second_city = ui.input(t("city", lang_cookie), value=current_secondary_city).classes('w-full mt-2')
                    second_postal_code = ui.input(t("postal_code", lang_cookie), value=current_secondary_postal_code).classes('w-full mt-2')
                second_address_details = ui.input(t("address_details", lang_cookie), value=current_secondary_details).classes('w-full mt-2')

            def save_changes():

                """Sauvegarde les informations renseignées en base ou dans les cookies"""
                
                # Sauvegarde max distance
                if ENABLE_SET_DISTANCE_LIMIT:
                    ui.run_javascript(
                        f'''document.cookie = "max_distance={distance_input.value}; path=/; max-age={60*60*24*30}";'''
                    )

                # Sauvegarde adresse et numéro de téléphone
                new_phone = phone_number.value
                new_street = address.value
                new_city = city.value
                new_postal_code = postal_code.value
                new_address_details = address_details.value
                secondary_address_street = second_address.value
                secondary_address_city = second_city.value
                secondary_address_postal_code = second_postal_code.value
                secondary_address_details = second_address_details.value

                # Mise à jour en base
                update_user(
                    user_id=user_id,
                    email=None,
                    password=None,
                    phone_number=new_phone,
                    main_address_street=new_street,
                    main_address_city=new_city,
                    main_address_postal_code=new_postal_code,
                    main_address_details=new_address_details,
                    secondary_address_street=secondary_address_street,
                    secondary_address_city=secondary_address_city,
                    secondary_address_postal_code=secondary_address_postal_code,
                    secondary_address_details=secondary_address_details
                )

                logger.info("User info updated", extra={"user_id": user_id})
                ui.notify(t("update_info", lang_cookie), color='positive')

            with ui.row().classes('w-full justify-center mt-4'):
                ui.button(t("save_2", lang_cookie), on_click=save_changes).classes('btn-success')


        # === Section 2 : Compte (email + mot de passe) ===
        with ui.expansion(icon='account_circle', text=t("account_info", lang_cookie)).classes('w-full bg-white/90 rounded-xl shadow-md mt-4'):

            email = ui.input(t("email", lang_cookie), value=current_email).classes('w-full mt-2')
            password = ui.input(
                t("change_password", lang_cookie),
                password=True,
                password_toggle_button=True
            ).classes('w-full mt-2')

            def save_changes_user_info():

                """Sauvegarde les informations renseignées en base"""

                new_email = email.value.strip() or None
                new_password = password.value.strip() or None

                if new_password:
                    pwd_hash = hash_password(new_password)
                    update_user(user_id, new_email, pwd_hash)
                else:
                    update_user(user_id, new_email, None)

                logger.info("User connection info updated", extra={"user_id": user_id})
                ui.notify(t("update_info", lang_cookie), color='positive')

            with ui.row().classes('w-full justify-center mt-4'):
                ui.button(t("save_2", lang_cookie), on_click=save_changes_user_info).classes('btn-success mt-4')


        # === Section 3 : Historique des commandes ===
        with ui.expansion(icon='shopping_bag', text=t("order_history", lang_cookie)).classes('w-full bg-white/90 rounded-xl shadow-md mt-4'):

            orders = get_order_history(user_id)

            with ui.column().classes("items-center w-full mt-2"):
                if not orders:
                    ui.label(t("no_order", lang_cookie)).classes("text-gray-500 italic mt-2 text-center")
                else:
                    # Conteneur centré pour les cartes
                    with ui.column().classes("w-full max-w-3xl items-center justify-center gap-4"):
                        for order_id, date, total, items in orders[:10]:
                            with ui.card().classes(
                                "w-full bg-white/90 shadow-lg rounded-xl p-6 border border-gray-200 hover:shadow-xl transition-all duration-300"
                            ):
                                with ui.row().classes("justify-between items-start mb-2 w-full"):
                                    with ui.column().classes("gap-0"):
                                        ui.label(f"{t('order_number', lang_cookie)} {order_id}").classes(
                                            "text-lg font-semibold text-gray-800"
                                        )
                                        ui.label(date).classes("text-sm text-gray-500 italic")

                                    ui.button(
                                        icon='file_download',
                                        on_click=lambda order_id=order_id: ui.run_javascript(
                                            f"window.open('/generate_order_pdf?order_id={order_id}', '_blank')"
                                        )
                                    ).props('round dense flat').classes('text-gray-600 hover:text-green-600 transition')

                                ui.label(f"{t('articles_list', lang_cookie)} {items}").classes("text-gray-700")
                                ui.label(f"{t('total', lang_cookie)} {total:.2f} €").classes(
                                    "font-bold text-green-600 text-lg mt-2"
                                )


        # === Section 4 : Historique des visites ===
        with ui.expansion(icon='history', text=t("visit_history", lang_cookie)).classes('w-full bg-white/90 rounded-xl shadow-md mt-4'):

            history = get_visit_history(user_id)
            if not history:
                ui.label(t("no_visit", lang_cookie)).classes("text-gray-400 italic mt-2")
            else:
                for page, info in sorted(history.items(), key=lambda x: x[1][1], reverse=True)[:20]:
                    display_page, count = info
                    ui.label(
                        f"{display_page} : {count} "
                        f"{t('visits', lang_cookie) if count > 1 else t('visit', lang_cookie)}"
                    ).classes("text-black bg-black/10 px-3 py-2 rounded-lg w-full text-center hover:bg-black/20 transition")

        
        # === Section 5 : Aide et contact ===
        with ui.expansion(icon='help_outline', text=t("help_contact", lang_cookie), value=open_contact).classes(
            'w-full bg-white/90 rounded-xl shadow-md mt-4').props('id="exp-contact"'
        ):
            
            ui.label(t("need_help", lang_cookie)).classes('text-lg font-semibold mb-2 text-center')
            ui.label(t("contact_intro", lang_cookie)).classes('text-gray-600 mb-4 text-center')

            with ui.column().classes('items-center gap-3 w-full'):
                # === Email de contact ===
                with ui.row().classes('items-center justify-center gap-2'):
                    ui.icon('email').classes('text-green-600')
                    support_mail = get_setting("support_email") or ""
                    ui.label(support_mail).classes('text-gray-700 text-base font-medium')

                # === Téléphone ===
                with ui.row().classes('items-center justify-center gap-2'):
                    ui.icon('call').classes('text-green-600')
                    phone = get_setting("support_phone") or ""
                    ui.label(phone).classes('text-gray-700 text-base font-medium')

                # === FAQ / Aide ===
                with ui.dialog() as faq_dialog, ui.card().classes('max-w-2xl p-6 rounded-2xl shadow-xl bg-white'):
                    
                    with ui.row().classes('w-full justify-between items-center mb-4'):
                        ui.icon('help').classes('text-blue-500 text-2xl')
                        ui.label(t("faq", lang_cookie)).classes('text-xl font-bold text-gray-800')
                        ui.button(icon='close', on_click=faq_dialog.close).props('flat round dense').classes('ml-auto')

                    ui.separator()

                    # === Contenu FAQ ===
                    with ui.column().classes('mt-4 space-y-3 text-gray-700'):
                        ui.label(t("faq_question_1", lang_cookie))
                        ui.label(t("faq_answer_1", lang_cookie)).classes('text-sm text-gray-600 ml-4')

                        ui.label(t("faq_question_2", lang_cookie))
                        ui.label(t("faq_answer_2", lang_cookie)).classes('text-sm text-gray-600 ml-4')

                        ui.label(t("faq_question_3", lang_cookie))
                        ui.label(t("faq_answer_3", lang_cookie)).classes('text-sm text-gray-600 ml-4')

                        ui.label(t("faq_question_4", lang_cookie))
                        ui.label(f"{t('faq_answer_4', lang_cookie)}{'support@votresite.fr'}").classes('text-sm text-gray-600 ml-4')

                        ui.label(t("faq_question_5", lang_cookie))
                        ui.label(t("faq_answer_5", lang_cookie)).classes('text-sm text-gray-600 ml-4')

                    ui.separator().classes('my-4')
                    ui.button(t("close", lang_cookie), on_click=faq_dialog.close).props('unelevated color=gray').classes('self-end mt-2')

                # === Bouton pour ouvrir la FAQ ===
                ui.button(
                    t("open_faq", lang_cookie),
                    icon='help_outline',
                    on_click=faq_dialog.open
                ).classes('btn-secondary mt-3')

                # === Message personnalisé ===
                ui.label(t("support_msg", lang_cookie)).classes('text-sm text-gray-500 italic mt-2 text-center')


    # === Zoom sur la section Contact si paramètre 'open_contact' ===
    if open_contact:
        ui.run_javascript(f"""
            const el = document.getElementById("exp-contact");
            if (el) {{
                setTimeout(() => {{
                    el.scrollIntoView({{behavior:'smooth', block:'center'}});
                }}, 300);
            }}
        """)