"""
Application entry point for PharmaLink.
"""

import os
import importlib
from pathlib import Path

from fastapi.staticfiles import StaticFiles
from nicegui import app, ui

# ----------------------------
# Project paths
# ----------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"

DATA_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

# ----------------------------
# Static files
# ----------------------------

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount(
    "/data/images",
    StaticFiles(directory=str(DATA_DIR / "images")),
    name="images",
)

# ----------------------------
# Page imports (side-effect based)
# ----------------------------

from routes import (
    admin_panel,
    details,
    home,
    in_progress,
    in_progress_order,
    itinerary,
    login,
    map,
    order,
    panier,
    profil,
    terms,
    thanks,
    wallet,
)

from routes.admin import analytics, orders, pharmacies, products, settings, users
from routes.delivery import (
    delivery_home,
    delivery_my,
    delivery_order,
    delivery_profil,
    delivery_wallet,
)

# ----------------------------
# Helpers
# ----------------------------

def _get_bool_env(var_name: str, default: bool) -> bool:
    value = os.getenv(var_name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _import_data_modules():
    """
    Import database bootstrap helpers.
    Root-based imports only (no package hacks).
    """
    create_db = importlib.import_module("data.create_db")
    migrate = importlib.import_module("data.migrate_json_to_sql")
    return create_db, migrate


# ----------------------------
# Main bootstrap
# ----------------------------

def main() -> None:
    create_db_module, migrate_module = _import_data_modules()

    db_file = DATA_DIR / "data.db"

    if not db_file.exists():
        import sqlite3

        print("📂 Base de données inexistante, création en cours...")
        conn = sqlite3.connect(db_file)

        create_db_module.init_db(conn)

        print("🚀 Migration des données produits et pharmacies...")
        migrate_module.migrate_products(conn)
        migrate_module.migrate_pharmacies(conn)
        migrate_module.migrate_settings(conn)

        conn.close()
        print("🎉 Migration terminée avec succès.")
    else:
        print(f"📂 Base de données trouvée : {db_file}")

    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8080"))
    reload_app = _get_bool_env("APP_RELOAD", False)

    ui.run(
        title="PharmaLink",
        host=host,
        port=port,
        reload=reload_app,
        storage_secret=os.getenv("APP_STORAGE_SECRET", "change-me"),
    )


# ----------------------------
# Entrypoint
# ----------------------------

if __name__ == "__main__":
    main()
