import shutil
from pathlib import Path


def backup_db(db_path: str = "data.db", backup_path: str = "data_backup.db"):

    """
    Crée une sauvegarde du fichier SQLite `db_path` dans `backup_path`.
    Si le backup existe déjà, il est écrasé.
    """
    
    src = Path(db_path)
    dst = Path(backup_path)

    if not src.exists():
        raise FileNotFoundError(f"⚠️ La base de données {db_path} est introuvable.")

    shutil.copy2(src, dst)
    print(f"✅ Sauvegarde créée : {dst}")


if __name__ == "__main__":
    backup_db()