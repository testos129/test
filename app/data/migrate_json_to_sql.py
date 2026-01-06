import json
import sqlite3
from pathlib import Path
from collections import Counter


# chemins des fichiers
REVIEWS_FILE = Path("data/reviews.json")
USERS_FILE = Path("data/users.json")
PRODUCTS_FILE = Path("data/products.json")
PHARMACIES_FILE = Path("data/pharmacies.json")
USER_PRODUCT_FILE = Path("data/user_product_interactions.json")
SETTINGS_FILE = Path("data/settings.json")
DB_FILE = Path("data/data.db")


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

        -- Statuts utilisateur
        is_delivery_person BOOLEAN DEFAULT 0,
        is_admin BOOLEAN DEFAULT 0,
        is_confirmed BOOLEAN DEFAULT 0,
        allow_comments BOOLEAN DEFAULT 1,

        -- Vérification du compte
        confirmation_code TEXT,
        code_expiration_date DATETIME,

        -- Informations de contact
        phone_number TEXT,

        -- Adresse principale
        main_address_street TEXT,
        main_address_city TEXT,
        main_address_postal_code TEXT,
        main_address_details TEXT,

        -- Adresse secondaire
        secondary_address_street TEXT,
        secondary_address_city TEXT,
        secondary_address_postal_code TEXT,
        secondary_address_details TEXT,
                
        -- Coordonnées utilisateur
        current_lat REAL,
        current_lng REAL,
        current_coords_date DATETIME
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
        address_details TEXT,
        delivery_person_id INTEGER,
        order_code TEXT,
        close_date TEXT,
        user_notified BOOLEAN DEFAULT 0,
        credited BOOLEAN DEFAULT 0,
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
        description_fr TEXT,
        description_en TEXT,
        reference_fr TEXT,
        reference_en TEXT,
        category TEXT,
        age_group TEXT,  
        estimated_price REAL,       
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


def migrate_users(conn):

    """Migrer users.json vers la base SQLite."""
    
    if not USERS_FILE.exists():
        print("⚠️ users.json introuvable, migration ignorée.")
        return

    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users_data = json.load(f)

    cur = conn.cursor()

    for user_id, user_info in users_data.items():
        # 1. Insérer l'utilisateur
        cur.execute("""
            INSERT OR IGNORE INTO users (
                id, username, password, email,
                is_delivery_person, is_admin, is_confirmed, allow_comments,
                confirmation_code, code_expiration_date,
                phone_number,
                main_address_street, main_address_city, main_address_postal_code, main_address_details,
                secondary_address_street, secondary_address_city, secondary_address_postal_code, secondary_address_details,
                current_lat, current_lng, current_coords_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = excluded.username,
                password = excluded.password,
                email = excluded.email,
                is_delivery_person = excluded.is_delivery_person,
                is_admin = excluded.is_admin,
                is_confirmed = excluded.is_confirmed,
                allow_comments = excluded.allow_comments,
                confirmation_code = excluded.confirmation_code,
                code_expiration_date = excluded.code_expiration_date,
                phone_number = excluded.phone_number,
                main_address_street = excluded.main_address_street,
                main_address_city = excluded.main_address_city,
                main_address_postal_code = excluded.main_address_postal_code,
                main_address_details = excluded.main_address_details,
                secondary_address_street = excluded.secondary_address_street,
                secondary_address_city = excluded.secondary_address_city,
                secondary_address_postal_code = excluded.secondary_address_postal_code,
                secondary_address_details = excluded.secondary_address_details,
                current_lat = excluded.current_lat,
                current_lng = excluded.current_lng,
                current_coords_date = excluded.current_coords_date
        """, (
            user_id,
            user_info.get("name"),
            user_info.get("password"),
            user_info.get("email"),
            user_info.get("is_delivery_person", False),
            user_info.get("is_admin", False),
            user_info.get("is_confirmed", False),
            user_info.get("allow_comments", True),
            user_info.get("confirmation_code", None),
            user_info.get("code_expiration_date", None),
            user_info.get("phone_number", None),
            user_info.get("main_address_street", None),
            user_info.get("main_address_city", None),
            user_info.get("main_address_postal_code", None),
            user_info.get("main_address_details", None),
            user_info.get("secondary_address_street", None),
            user_info.get("secondary_address_city", None),
            user_info.get("secondary_address_postal_code", None),
            user_info.get("secondary_address_details", None),
            user_info.get("current_lat", None),
            user_info.get("current_lng", None),
            user_info.get("current_coords_date", None)
        ))
        conn.commit()

        # 2. Historique navigation
        history = user_info.get("history", {})
        for display_page, data in history.items():
            visits = data.get("visits", 0)
            raw_page = data.get("raw_page", display_page)  # fallback si jamais raw_page manquant
            cur.execute("""
                INSERT INTO user_history (user_id, page, display_page, visits)
                VALUES (?, ?, ?, ?)
            """, (user_id, raw_page, display_page, visits))

        # 3. Panier
        panier_items = user_info.get("panier", {})
        for product_id, quantity in panier_items.items():
            cur.execute("""
                INSERT INTO panier (user_id, product_id, quantity)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, product_id) DO UPDATE
                SET quantity = excluded.quantity
            """, (user_id, int(product_id), quantity))

        # 4. Wallet
        wallet = user_info.get("wallet_data", {})
        balance = wallet.get("balance", 0.0)
        cur.execute("""
            INSERT INTO wallets (user_id, balance)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET balance = excluded.balance
        """, (user_id, balance))

        # La table wallet_history est supprimée avant synchronisation pour éviter l'ajout de doublons depuis le json car il n'y a pas d'unicité
        cur.execute("DELETE FROM wallet_history WHERE user_id=?", (user_id,))

        for date, amount, desc in wallet.get("history", []):
            cur.execute("""
                INSERT INTO wallet_history (user_id, date, amount, description)
                VALUES (?, ?, ?, ?)
            """, (user_id, date, amount, desc))

        # 5. Orders
        orders = user_info.get("orders", {})

        for order_id, items in orders.items():
            for item in items:
                product_id = item.get("product_id")
                qty = item.get("qty", 1)
                total_price = item.get("total_price", 0.0)
                date = item.get("date")
                pharmacy_id = item.get("pharmacy_id", None)
                status = item.get("status")
                latitude = item.get("latitude", None)
                longitude = item.get("longitude", None)
                address = item.get("address", None)
                address_details = item.get("address_details", None)
                delivery_person_id = item.get("delivery_person_id", None)
                order_code = item.get("order_code", None)
                close_date = item.get("close_date", None)
                user_notified = item.get("user_notified", 0)
                credited = item.get("credited", 0)

                # Vérifier si une ligne existe déjà pour cet order_id + user_id + product_id
                cur.execute("""
                    SELECT id FROM orders
                    WHERE order_id = ? AND user_id = ? AND product_id = ?
                """, (order_id, user_id, product_id))
                row = cur.fetchone()

                if row:
                    # Mise à jour si déjà présent
                    cur.execute("""
                        UPDATE orders
                        SET qty = ?, total_price = ?, date = ?
                        WHERE id = ?
                    """, (qty, total_price, date, row[0]))
                else:
                    # Insertion sinon
                    cur.execute("""
                        INSERT INTO orders (
                            order_id, user_id, product_id, qty, total_price, pharmacy_id, date, 
                            status, latitude, longitude, address, address_details, delivery_person_id, order_code,
                            close_date, user_notified, credited
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (order_id, 
                          user_id, 
                          product_id, 
                          qty, 
                          total_price, 
                          pharmacy_id, 
                          date, 
                          status, 
                          latitude, 
                          longitude, 
                          address, 
                          address_details, 
                          delivery_person_id,
                          order_code,
                          close_date,
                          user_notified,
                          credited))


    conn.commit()
    print(f"✅ {len(users_data)} utilisateurs migrés.")


def migrate_reviews(conn):
    
    """Migrer reviews.json vers la base SQLite."""

    if not REVIEWS_FILE.exists():
        print("⚠️ reviews.json introuvable, migration ignorée.")
        return

    with open(REVIEWS_FILE, "r", encoding="utf-8") as f:
        reviews_data = json.load(f)

    cur = conn.cursor()

    total_reviews = 0
    for product_id, reviews in reviews_data.items():
        for review in reviews:
            username = review.get("user")

            # Récupérer l'user_id
            cur.execute("SELECT id FROM users WHERE username = ?", (username,))
            user = cur.fetchone()
            if not user:
                print(f"⚠️ Utilisateur '{username}' non trouvé, avis ignoré.")
                continue
            user_id = user[0]

            # Insérer ou mettre à jour l'avis
            cur.execute("""
                INSERT INTO reviews (product_id, user_id, rating, comment, date, modified, editing)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, product_id) DO UPDATE SET
                    rating = excluded.rating,
                    comment = excluded.comment,
                    date = excluded.date,
                    modified = excluded.modified,
                    editing = excluded.editing
            """, (
                int(product_id),
                user_id,
                review.get("rating"),
                review.get("comment"),
                review.get("date"),
                int(review.get("modified", False)),
                int(review.get("editing", False))
            ))

            total_reviews += 1

    conn.commit()
    print(f"✅ {total_reviews} avis migrés (un seul avis par utilisateur et produit).")


def migrate_products(conn):

    """Migrer products.json vers la base SQLite."""
    
    if not PRODUCTS_FILE.exists():
        print("⚠️ products.json introuvable, migration ignorée.")
        return

    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        products_data = json.load(f)

    cur = conn.cursor()

    for product_id, product in products_data.items():
        # Insertion produit
        cur.execute("""
            INSERT OR REPLACE INTO products
            (id, name, provider, image, description_fr, description_en, reference_fr, reference_en, category, age_group, estimated_price, allow_reviews, display_price, allow_order, display_recommendations, ordonnance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(product_id),
            product.get("name"),
            product.get("provider"),
            product.get("image"),
            product.get("description_fr"),
            product.get("description_en"),
            product.get("reference_fr"),
            product.get("reference_en"),
            product.get("category"),
            product.get("age_group"),
            product.get("estimated_price"),
            product.get("allow_reviews", True),
            product.get("display_price", True),
            product.get("allow_order", True),
            product.get("display_recommendations", True),
            product.get("ordonnance", False)
        ))

        # Nettoyage anciens composants/tags (si re-migration)
        cur.execute("DELETE FROM product_components WHERE product_id=?", (product_id,))
        cur.execute("DELETE FROM product_tags WHERE product_id=?", (product_id,))

        # Insertion composants
        for comp in product.get("component", []):
            cur.execute("""
                INSERT INTO product_components (product_id, component)
                VALUES (?, ?)
            """, (product_id, comp))

        # Insertion tags
        for tag in product.get("tags", []):
            cur.execute("""
                INSERT INTO product_tags (product_id, tag)
                VALUES (?, ?)
            """, (product_id, tag))


    conn.commit()
    print(f"✅ {len(products_data)} produits migrés.")


def migrate_pharmacies(conn):

    """Migrer pharmacies.json vers SQLite."""

    if not PHARMACIES_FILE.exists():
        print("⚠️ pharmacies.json introuvable, migration ignorée.")
        return

    with open(PHARMACIES_FILE, "r", encoding="utf-8") as f:
        pharmacies_data = json.load(f)

    cur = conn.cursor()
    total_pharmacies = 0
    total_products = 0

    for pharmacy_id, info in pharmacies_data.items():
        # Insérer la pharmacie
        name = info.get("name")
        address = info.get("address")
        latitude, longitude = info.get("coords", [None, None])
        phone_number = info.get("phone_number")

        cur.execute("""
            INSERT OR REPLACE INTO pharmacies (id, name, address, latitude, longitude, phone_number)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                address = excluded.address,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                phone_number = excluded.phone_number
        """, (int(pharmacy_id), name, address, latitude, longitude, phone_number))

        total_pharmacies += 1

        # Insérer les produits disponibles
        available_products = info.get("available_products", {})
        for product_id, pdata in available_products.items():
            price = pdata.get("price")
            qty = pdata.get("qty")

            cur.execute("""
                INSERT INTO pharmacy_products (pharmacy_id, product_id, price, qty)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(pharmacy_id, product_id) DO UPDATE
                SET price = excluded.price,
                    qty = excluded.qty
            """, (int(pharmacy_id), int(product_id), price, qty))

            total_products += 1

    conn.commit()
    print(f"✅ {total_pharmacies} pharmacies et {total_products} produits migrés.")


def migrate_user_product_interactions(conn):

    """Migrer les interactions user/product."""

    if not USER_PRODUCT_FILE.exists():
        print("⚠️ user_product_interactions.json introuvable, migration ignorée.")
        return

    with open(USER_PRODUCT_FILE, "r", encoding="utf-8") as f:
        interactions = json.load(f)

    cur = conn.cursor()

    for user_id, products in interactions.items():
        for product_id, score in products.items():
            cur.execute("""
                INSERT INTO user_product_interactions (user_id, product_id, score)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, product_id) DO UPDATE 
                SET score = excluded.score
            """, (int(user_id), int(product_id), score))

    conn.commit()

    print(f"✅ Import terminé : {len(interactions)} utilisateurs → base de données mise à jour")


def migrate_settings(conn):

    """Migrer les paramètres depuis settings.json vers SQLite."""

    if not SETTINGS_FILE.exists():
        print("⚠️ settings.json introuvable, migration ignorée.")
        return

    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        settings_data = json.load(f)

    cur = conn.cursor()

    for key, value in settings_data.items():
        cur.execute("""
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, str(value)))

    conn.commit()
    print(f"✅ {len(settings_data)} paramètres migrés.")


def main():

    print("🚀 Démarrage de la migration...")
    conn = sqlite3.connect(DB_FILE)

    init_db(conn)
    migrate_users(conn)
    migrate_reviews(conn)
    migrate_products(conn)
    migrate_pharmacies(conn)
    migrate_user_product_interactions(conn)
    migrate_settings(conn)
    conn.close()
    print("🎉 Migration terminée avec succès.")


if __name__ == "__main__":
    main()

# Lancement du script : python -m data.migrate_json_to_sql