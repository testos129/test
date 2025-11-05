from nicegui import ui, app
from pathlib import Path
from fastapi.staticfiles import StaticFiles
import os


def _get_bool_env(var_name: str, default: bool) -> bool:
    """Return a boolean value from an environment variable."""
    value = os.getenv(var_name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

# Import des pages
from routes import home, details, login, map, profil, panier, order, thanks, wallet, itinerary, admin_panel, in_progress
from routes.admin import users, products, pharmacies, settings
from routes.delivery import delivery_home, delivery_order, delivery_profil, delivery_my


if __name__ in {"__main__", "__mp_main__"}:

    # Initialisation des tables (vides) dans la base de données si elle n'existe pas
    DB_FILE = Path(r"data/data.db")

    app.mount("/data/images", StaticFiles(directory="data/images"), name="images")

    if not DB_FILE.exists():

         import sqlite3
         from data.create_db import init_db
         from data.migrate_json_to_sql import migrate_products, migrate_pharmacies, migrate_settings

         conn = sqlite3.connect(DB_FILE)
         print("📂 Base de données inexistante, création en cours...")
         init_db(conn)
         print("🚀 Migration des données produits et pharmacies...")
         migrate_products(conn)
         migrate_pharmacies(conn)
         migrate_settings(conn)
         print("🎉 Migration terminée avec succès.")
         conn.close()
    else:
         print(f"📂 Base de données trouvées dans {DB_FILE}")


    # Lancement de l'application
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8080"))
    reload_app = _get_bool_env("APP_RELOAD", True)

    ui.run(
        title="PharmaLink",
        reload=reload_app,
        host=host,
        port=port,
        storage_secret=os.getenv("APP_STORAGE_SECRET", "uwu"),
    )
