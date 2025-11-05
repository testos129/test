from nicegui import ui, app
from fastapi.responses import RedirectResponse
import datetime
from fastapi import Request

from app.services.auth import get_current_user, sessions
from app.components.navbar import navbar
from app.components.theme import apply_background
from app.services.users import get_user_info, get_connection
from app.services.settings import get_setting, set_setting
from app.translations.translations import t


@ui.page('/admin/settings')
def admin_settings(request: Request):

    """Page de gestion des paramètres pour les administrateurs."""

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

    # Bouton retour
    with ui.row().classes('w-full p-4 sticky top-0 left-0 z-50 bg-transparent justify-start'):
        ui.button('⬅', on_click=lambda: ui.run_javascript('window.history.back()')) \
            .props('unelevated') \
            .classes('btn-back shadow-lg')

    # === Contenu ===
    with ui.column().classes('items-center w-full max-w-6xl mx-auto p-8 gap-10'):

        # === Titre ===
        ui.label(t("site_parameters_and_analytics", lang_cookie)).classes(
            'text-4xl font-extrabold text-center mb-6'
        )

        with ui.row().classes("w-full gap-6 flex-wrap justify-center"):
            # Nombre d'utilisateurs
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM users")
                users_count = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM products")
                products_count = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM pharmacies")
                pharmacies_count = cur.fetchone()[0]

            with ui.card().classes("p-6 w-60 text-center bg-white shadow-md rounded-xl"):
                ui.label(f"{users_count}").classes("text-3xl font-bold")
                ui.label(t("users", lang_cookie)).classes("text-gray-600")

            with ui.card().classes("p-6 w-60 text-center bg-white shadow-md rounded-xl"):
                ui.label(f"{products_count}").classes("text-3xl font-bold")
                ui.label(t("products", lang_cookie)).classes("text-gray-600")

            with ui.card().classes("p-6 w-60 text-center bg-white shadow-md rounded-xl"):
                ui.label(f"{pharmacies_count}").classes("text-3xl font-bold")
                ui.label(t("pharmacies", lang_cookie)).classes("text-gray-600")

        # === Pages les plus visitées ===
        with ui.card().classes("w-full max-w-6xl mx-auto p-6 bg-white shadow-md rounded-xl"):
            ui.label(t("most_view_pages", lang_cookie)).classes("text-xl font-semibold mb-4")

            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT COALESCE(display_page, page) as page, SUM(visits) as total_visits
                    FROM user_history
                    GROUP BY page
                    ORDER BY total_visits DESC
                    LIMIT 5
                """)
                pages = list(reversed(cur.fetchall()))

            labels = [p[0] for p in pages]
            values = [p[1] for p in pages]

            ui.echart(
                {
                    "xAxis": {
                        "type": "category",
                        "data": labels,
                        "axisLabel": {"rotate": 45, "interval": 0},  # afficher toutes les étiquettes
                    },
                    "yAxis": {"type": "value"},
                    "series": [
                        {
                            "data": values,
                            "type": "bar",
                            "itemStyle": {"color": "#3B82F6"},
                        }
                    ],
                    "tooltip": {"trigger": "axis"},
                }
            ).classes("w-full h-64")

        
        # === Graphe des ventes par jour ===
        with ui.card().classes("w-full max-w-6xl mx-auto p-6 bg-white shadow-md rounded-xl mt-6"):
            ui.label(t("daily_sales", lang_cookie)).classes("text-xl font-semibold mb-4")

            # Sélecteur pour la plage de temps
            days_options = {7: f"7{t('days', lang_cookie)}", 
                            30: f"30{t('days', lang_cookie)}", 
                            60: f"60{t('days', lang_cookie)}", 
                            90: f"90{t('days', lang_cookie)}", 
                            180: f"6{t('months', lang_cookie)}", 
                            365: f"1{t('year', lang_cookie)}"}
            days_select = ui.select(days_options, value=60, label=t("time_range", lang_cookie)).classes("mb-4 w-40")

            chart_container = ui.column().classes("w-full")

            def update_chart(days: int):

                """Met à jour le graphe des ventes en fonction de la plage de temps sélectionnée."""

                chart_container.clear()

                with get_connection() as conn:
                    cur = conn.cursor()

                    start_date = (datetime.date.today() - datetime.timedelta(days=days - 1)).isoformat()

                    # Récupération des ventes par jour
                    cur.execute("""
                        SELECT date(o.date) as day, SUM(o.qty) as total_sales
                        FROM orders o
                        WHERE date(o.date) >= ?
                        GROUP BY day
                        ORDER BY day ASC
                    """, (start_date,))
                    sales_data = cur.fetchall()

                # Générer toutes les dates sur la plage sélectionnée
                date_list = [(datetime.date.today() - datetime.timedelta(days=i)).isoformat() for i in reversed(range(days))]
                sales_dict = {row[0]: row[1] for row in sales_data}
                values = [sales_dict.get(day, 0) for day in date_list]

                with chart_container:
                    ui.echart(
                        {
                            "xAxis": {
                                "type": "category",
                                "data": date_list,
                                "axisLabel": {
                                    "interval": max(1, days // 10),  # réduire le nombre de labels si plage grande
                                    "rotate": 45,
                                },
                            },
                            "yAxis": {"type": "value"},
                            "series": [
                                {
                                    "data": values,
                                    "type": "line",
                                    "smooth": True,
                                    "itemStyle": {"color": "#10B981"},
                                }
                            ],
                            "tooltip": {"trigger": "axis"},
                        }
                    ).classes("w-full h-64")

            # Charger le graphe initial avec la valeur par défaut (60 jours)
            update_chart(days_select.value)

            # Recharger le graphe quand l’utilisateur change la plage
            days_select.on_value_change(lambda e: update_chart(int(e.value)))


        # === Produits les plus achetés ===
        with ui.card().classes("w-full max-w-6xl mx-auto p-6 bg-white shadow-md rounded-xl mt-6"):
            ui.label(t("most_bought_products", lang_cookie)).classes("text-xl font-semibold mb-4")

            with get_connection() as conn:
                cur = conn.cursor()
                # On récupère le top 5 des produits en fonction de la quantité totale achetée
                cur.execute("""
                    SELECT p.name, SUM(o.qty) as total_qty
                    FROM orders o
                    JOIN products p ON o.product_id = p.id
                    GROUP BY o.product_id
                    ORDER BY total_qty DESC
                    LIMIT 5
                """)
                products = list(reversed(cur.fetchall()))  # pour affichage croissant

            labels = [p[0] for p in products]
            values = [p[1] for p in products]

            ui.echart(
                {
                    "xAxis": {
                        "type": "category",
                        "data": labels,
                        "axisLabel": {"rotate": 45, "interval": 0},  # afficher toutes les étiquettes
                    },
                    "yAxis": {"type": "value"},
                    "series": [
                        {
                            "data": values,
                            "type": "bar",
                            "itemStyle": {"color": "#F59E0B"},  # couleur orange pour différencier
                        }
                    ],
                    "tooltip": {"trigger": "axis"},
                }
            ).classes("w-full h-64")


        # === Paramètres administratifs ===
        with ui.card().classes("w-full p-6 bg-white shadow-md rounded-xl"):
            ui.label(t("site_settings", lang_cookie)).classes("text-xl font-semibold mb-4")
            
            site_name_input = ui.input(t("site_name", lang_cookie), value=get_setting("site_name")).classes("w-full")
            site_version_input = ui.input(t("site_version", lang_cookie), value=get_setting("site_version")).classes("w-full")
            site_logo_input = ui.input(t("logo_url", lang_cookie), value=get_setting("site_logo")).classes("w-full")
            site_theme_input = ui.input(t("theme_color", lang_cookie), value=get_setting("site_theme")).classes("w-full")
            admin_email_input = ui.input(t("admin_email", lang_cookie), value=get_setting("admin_email")).classes("w-full")
            support_email_input = ui.input(t("support_email", lang_cookie), value=get_setting("support_email")).classes("w-full")
            password_policy_input = ui.input(t("min_password_lenght", lang_cookie), value=get_setting("password_policy_min_length")).props("type=number step=1 min=1").classes("w-full")
            default_currency_input = ui.input(t("default_currency", lang_cookie), value=get_setting("default_currency")).classes("w-full")
            items_per_page_input = ui.input(t("products_per_page", lang_cookie), value=get_setting("display_items_per_page")).props("type=number step=1 min=1").classes("w-full")
            free_delivery_input = ui.input(t("free_delivery_threshold", lang_cookie), value=get_setting("free_delivery_threshold")).props("type=number").classes("w-full")
            support_phone_input = ui.input(t("support_phone", lang_cookie), value=get_setting("support_phone")).classes("w-full")
            max_order_delivery = ui.input(t("max_order_delivery", lang_cookie), value=get_setting("max_order_delivery")).props("type=number step=1 min=1").classes("w-full")
            guest_checkout_input = ui.checkbox(t("allow_guest_checkout", lang_cookie), value=get_setting("allow_guest_checkout")).classes("w-full")
            show_notifications_input = ui.checkbox(t("show_notifications", lang_cookie), value=get_setting("show_notifications")).classes("w-full")   
            user_registration_input = ui.checkbox(t("allow_user_registration", lang_cookie), value=get_setting("allow_user_registration")).classes("w-full")
            maintenance_mode_input = ui.checkbox(t("maintenance_mode", lang_cookie), value=get_setting("maintenance_mode")).classes("w-full")         

            def save_settings():

                """Sauvegarde les paramètres modifiés."""

                inputs = [("site_name", site_name_input), 
                          ("site_version", site_version_input), 
                          ("site_logo", site_logo_input),
                          ("site_theme", site_theme_input),
                          ("admin_email", admin_email_input),
                          ("support_email", support_email_input),
                          ("password_policy_min_length", password_policy_input),
                          ("allow_user_registration", user_registration_input),
                          ("maintenance_mode", maintenance_mode_input),
                          ("default_currency", default_currency_input),
                          ("display_items_per_page", items_per_page_input),
                          ("free_delivery_threshold", free_delivery_input),
                          ("allow_guest_checkout", guest_checkout_input),
                          ("support_phone", support_phone_input),
                          ("show_notifications", show_notifications_input),
                          ("max_order_delivery", max_order_delivery)
                         ]

                for key, input_widget in inputs:
                    value = input_widget.value
                    if isinstance(value, bool):
                        value = int(value)  # stocker les booléens comme 0/1
                    set_setting(key, value)

                ui.notify(t("parameters_updated", lang_cookie), color="positive")


            ui.button(t("save_2", lang_cookie), on_click=save_settings).classes(
                "bg-blue-500 text-white px-6 py-2 rounded-lg hover:bg-blue-600 mt-4"
            )