import sqlite3
from pathlib import Path


DB_FILE = Path("data.db")


def init_db(conn):

    """Créer les tables SQLite si elles n'existent pas."""

    cur = conn.cursor()

    # Table des commentaires
    cur.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        rating INTEGER NOT NULL,
        comment TEXT,
        date TEXT,
        modified BOOLEAN,
        editing BOOLEAN,
        UNIQUE(user_id, product_id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)

    # Table des utilisateurs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        email TEXT UNIQUE,
        is_delivery_person BOOLEAN DEFAULT 0,
        is_admin BOOLEAN DEFAULT 0,
        is_confirmed BOOLEAN DEFAULT 0,
        allow_comments BOOLEAN DEFAULT 1,
        confirmation_code TEXT,
        code_expiration_date DATETIME,
        delivery_address TEXT
    )
    """)

    # Table de l'historique des utilisateurs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        page TEXT,           -- page brute (URL)
        display_page TEXT,   -- version lisible
        visits INTEGER,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    
    # Table du panier des utilisateurs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS panier (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        UNIQUE(user_id, product_id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)

    # Table de l'historique du wallet des utilisateurs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS wallet_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        date TEXT,
        amount REAL,
        description TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    # Table du montant de wallet des utilisateurs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS wallets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE,
        balance REAL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    # Table des commandes
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,    -- identifiant unique de la ligne (optionnel)
        order_id INTEGER NOT NULL,               -- identifiant de la commande (peut se répéter)
        user_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        qty INTEGER NOT NULL,
        total_price REAL NOT NULL,
        pharmacy_id INTEGER,
        date TEXT NOT NULL,
        status TEXT NOT NULL,
        latitude REAL,
        longitude REAL,
        address TEXT,
        delivery_person_id INTEGER,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(product_id) REFERENCES products(id)
    );
    """)

    # Table des produits
    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        provider TEXT,
        image TEXT,
        description TEXT,
        reference TEXT,
        category TEXT,
        age_group TEXT,        
        allow_reviews BOOLEAN,
        display_price BOOLEAN,
        allow_order BOOLEAN,
        display_recommendations BOOLEAN,
        ordonnance BOOLEAN
    )
    """)

    # Table des composants (relation n-n avec produits)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS product_components (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        component TEXT NOT NULL,
        FOREIGN KEY(product_id) REFERENCES products(id)
    )
    """)

    # Table des tags (relation n-n avec produits)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS product_tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        tag TEXT NOT NULL,
        FOREIGN KEY(product_id) REFERENCES products(id)
    )
    """)

    # Table des pharmacies
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pharmacies (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        address TEXT,
        latitude REAL,
        longitude REAL,
        phone_number TEXT
    )
    """)

    # Table des produits disponibles dans les pharmacies
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pharmacy_products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pharmacy_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        price REAL NOT NULL,
        qty INTEGER NOT NULL,
        UNIQUE(pharmacy_id, product_id),
        FOREIGN KEY(pharmacy_id) REFERENCES pharmacies(id)
    )
    """)

    # Table des interactions produits/utilisateurs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_product_interactions (
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            score INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, product_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)

    # Table des paramètres
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    conn.commit()
    print("✅ Tables créées (si elles n'existaient pas déjà).")


def main():

    conn = sqlite3.connect(DB_FILE)

    init_db(conn)
    conn.close()
    print("🎉 Création de la base terminée avec succès.")


if __name__ == "__main__":
    main()