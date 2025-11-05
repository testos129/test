"""Application entry point for PharmaLink."""

from pathlib import Path
import importlib
import os
import sys

CURRENT_DIR = Path(__file__).resolve().parent
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(CURRENT_DIR.parent))
    __package__ = CURRENT_DIR.name


from fastapi.staticfiles import StaticFiles
from nicegui import app, ui

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'


def _get_bool_env(var_name: str, default: bool) -> bool:
    """Return a boolean value from an environment variable."""
    value = os.getenv(var_name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

# Import des pages
from app.routes import (
    admin_panel,
    details,
    home,
    in_progress,
    itinerary,
    login,
    map,
    order,
    panier,
    profil,
    thanks,
    wallet,
)
from app.routes.admin import pharmacies, products, settings, users
from app.routes.delivery import (
    delivery_home,
    delivery_my,
    delivery_order,
    delivery_profil,
)



def _resolve_module(*candidates: str):
    """Return the first importable module from the provided candidates."""
    for module_name in candidates:
        if not module_name:
            continue
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError(
        f"Unable to import any of the candidate modules: {', '.join(c for c in candidates if c)}"
    )


def _load_data_modules():
    """Load database bootstrap helpers regardless of execution context."""
    package_name = __package__ or CURRENT_DIR.name
    create_db_module = _resolve_module(
        "app.data.create_db",
        f"{package_name}.data.create_db" if package_name else None,
        "data.create_db",
    )
    migrate_module = _resolve_module(
        "app.data.migrate_json_to_sql",
        f"{package_name}.data.migrate_json_to_sql" if package_name else None,
        "data.migrate_json_to_sql",
    )
    return create_db_module, migrate_module


def main():
    """Application bootstrap routine used for both script and module execution."""

    create_db_module, migrate_module = _load_data_modules()

    # Initialisation des tables (vides) dans la base de données si elle n'existe pas
    DB_FILE = DATA_DIR / "data.db"

    app.mount("/data/images", StaticFiles(directory=str(DATA_DIR / "images")), name="images")

    if not DB_FILE.exists():

        import sqlite3

        init_db = create_db_module.init_db
        migrate_pharmacies = migrate_module.migrate_pharmacies
        migrate_products = migrate_module.migrate_products
        migrate_settings = migrate_module.migrate_settings

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


if __name__ in {"__main__", "__mp_main__"}:
    main()

