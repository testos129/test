from nicegui import ui, app
from fastapi.responses import RedirectResponse
from datetime import datetime, date, timedelta
from fastapi import Request
import numpy as np

from services.auth import get_current_user
from components.navbar import navbar
from components.footer import footer_bar
from components.theme import apply_background
from services.users import get_user_info, get_connection, get_orders_grouped_by_status
from services.logging_setup import get_logger
from translations.translations import t


@ui.page('/admin/analytics')
def admin_analytics(request: Request):

    """Page d'analytics du site pour les administrateurs."""

    # === Setup initial ===

    # Récupération de l'utilisateur et application du style global, de la barre de navigation et des cookies
    user_id = get_current_user(request)
    if not user_id:
        host = request.client.host
        logger_default = get_logger('default')
        logger_default.info(f"Access denied for admin page analytics: no valid token, ip: {host}")
        return RedirectResponse('/')
    
    # Vérification des droits admin
    user_info = get_user_info(user_id)
    if not user_info.get('is_admin', False):
        logger_user = get_logger('nav')
        logger_user.info(f"Tried to open analytics page but was denied", extra={"user_id": user_id})
        return RedirectResponse('/home')
    
    apply_background()
    navbar(request)
    footer_bar(request)

    logger = get_logger('admin')
    logger.info("Analytics page consulted", extra={"admin_user_id": user_id})

    lang_cookie = request.cookies.get("language", "fr")

    # Bouton retour
    with ui.row().classes('w-full p-4 sticky top-0 left-0 z-50 bg-transparent justify-start'):
        ui.button('⬅', on_click=lambda: ui.run_javascript('window.history.back()')) \
            .props('unelevated') \
            .classes('btn-back shadow-lg')

    # === Contenu ===
    with ui.column().classes('items-center w-full max-w-6xl mx-auto p-8 gap-10'):

        # === Titre ===
        ui.label(t("site_analytics", lang_cookie)).classes(
            'text-4xl font-extrabold text-center mb-6'
        )

        # === Stats principales ===
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

                    start_date = (date.today() - timedelta(days=days - 1)).isoformat()

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
                date_list = [(date.today() - timedelta(days=i)).isoformat() for i in reversed(range(days))]
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


        # === Histogrammes des temps de commandes ===
        all_orders = get_orders_grouped_by_status()

        completed_orders = all_orders['completed']
        completed_orders_with_date = [order for order in completed_orders if order['close_date']]

        durations = []

        for order in completed_orders_with_date:
            start = datetime.strptime(order["date"], "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(order["close_date"], "%Y-%m-%d %H:%M:%S")

            diff_minutes = (end - start).total_seconds() / 60
            durations.append(round(diff_minutes, 2))


        counts, bins = np.histogram(durations, bins="auto")

        # Transformer les bornes en labels lisibles
        labels = [f"{int(bins[i])}-{int(bins[i+1])} min" for i in range(len(bins)-1)]

              
        with ui.card().classes("w-full max-w-6xl mx-auto p-6 bg-white shadow-md rounded-xl mt-6"):
            ui.label(t("order_duration", lang_cookie)).classes("text-xl font-semibold mb-4")

            ui.echart(
                {
                    "tooltip": {"trigger": "axis"},
                    "xAxis": {"type": "category", "data": labels},
                    "yAxis": {"type": "value"},
                    "series": [
                        {
                            "type": "bar",
                            "data": counts.tolist(),
                        }
                    ]
                }
            ).classes("w-full h-64")

