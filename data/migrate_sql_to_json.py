import sqlite3
import json
from pathlib import Path

# fichiers de sortie
USERS_FILE = Path("data/users.json")
REVIEWS_FILE = Path("data/reviews.json")
PRODUCTS_FILE = Path("data/products.json")
PHARMACIES_FILE = Path("data/pharmacies.json")
USER_PRODUCT_FILE = Path("data/user_product_interactions.json")
SETTINGS_FILE = Path("data/settings.json")
DB_FILE = Path("data/data.db")


def export_users(conn):

    """Exporter les utilisateurs et leurs données associées en JSON."""

    cur = conn.cursor()

    users_dict = {}

    # récupérer tous les utilisateurs
    cur.execute("""
        SELECT
            id, username, password, email,
            is_delivery_person, is_admin, is_confirmed, allow_comments,
            confirmation_code, code_expiration_date,
            phone_number,
            main_address_street, main_address_city, main_address_postal_code, main_address_details,
            secondary_address_street, secondary_address_city, secondary_address_postal_code, secondary_address_details,
            current_lat, current_lng, current_coords_date
        FROM users
    """)

    for (
        user_id, username, password, email,
        is_delivery_person, is_admin, is_confirmed, allow_comments,
        confirmation_code, code_expiration_date,
        phone_number,
        main_address_street, main_address_city, main_address_postal_code, main_address_details,
        secondary_address_street, secondary_address_city, secondary_address_postal_code, secondary_address_details,
        current_lat, current_lng, current_coords_date
    ) in cur.fetchall():

        user_info = {
            "name": username,
            "password": password,
            "email": email,
            "is_delivery_person": is_delivery_person,
            "is_admin": is_admin,
            "is_confirmed": is_confirmed,
            "allow_comments": allow_comments,
            "confirmation_code": confirmation_code,
            "code_expiration_date": code_expiration_date,
            "phone_number": phone_number,
            "main_address_street": main_address_street,
            "main_address_city": main_address_city,
            "main_address_postal_code": main_address_postal_code,
            "main_address_details": main_address_details,
            "secondary_address_street": secondary_address_street,
            "secondary_address_city": secondary_address_city,
            "secondary_address_postal_code": secondary_address_postal_code,
            "secondary_address_details": secondary_address_details,
            "current_lat": current_lat,
            "current_lng": current_lng,
            "current_coords_date": current_coords_date,
            "history": {},
            "panier": {},
            "wallet_data": {"balance": 0.0, "history": []},
            "orders": {}
        }

        # historique navigation
        cur.execute("SELECT page, display_page, visits FROM user_history WHERE user_id = ?", (user_id,))
        for page, display_page, visits in cur.fetchall():
            user_info["history"][display_page] = {
                "visits": visits,
                "raw_page": page
            }

        # panier
        cur.execute("SELECT product_id, quantity FROM panier WHERE user_id = ?", (user_id,))
        for product_id, quantity in cur.fetchall():
            user_info["panier"][str(product_id)] = quantity

        # wallet
        cur.execute("SELECT balance FROM wallets WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if row:
            user_info["wallet_data"]["balance"] = row[0]

        cur.execute("SELECT date, amount, description FROM wallet_history WHERE user_id = ?", (user_id,))
        for date, amount, desc in cur.fetchall():
            user_info["wallet_data"]["history"].append([date, amount, desc])

        # commandes / orders
        cur.execute("""
            SELECT order_id, product_id, qty, total_price, date, pharmacy_id, status, latitude, longitude,
                   address, address_details, delivery_person_id, order_code, close_date, user_notified, credited
            FROM orders
            WHERE user_id = ?
            ORDER BY order_id
        """, (user_id,))

        for (order_id, product_id, qty, total_price, date, pharmacy_id, status, 
             latitude, longitude, address, address_details, delivery_person_id, order_code, 
             close_date, user_notified, credited
        ) in cur.fetchall():
            
            if order_id not in user_info["orders"]:
                user_info["orders"][order_id] = []
                
            user_info["orders"][order_id].append({
                "product_id": product_id,
                "qty": qty,
                "total_price": total_price,
                "pharmacy_id": pharmacy_id,
                "date": date,
                "status": status,
                "latitude": latitude,
                "longitude": longitude,
                "address": address,
                "address_details": address_details,
                "delivery_person_id": delivery_person_id,
                "order_code": order_code,
                "close_date": close_date,
                "user_notified": user_notified,
                "credited": credited
            })

        users_dict[user_id] = user_info

    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users_dict, f, indent=4, ensure_ascii=False)

    print(f"✅ {len(users_dict)} utilisateurs exportés → {USERS_FILE}")


def export_reviews(conn):

    """Exporter les avis en JSON."""

    cur = conn.cursor()

    reviews_dict = {}

    # jointure pour récupérer l'username aussi
    cur.execute("""
        SELECT r.product_id, u.username, r.rating, r.comment, r.date, r.modified, r.editing
        FROM reviews r
        JOIN users u ON r.user_id = u.id
    """)

    for product_id, username, rating, comment, date, modified, editing in cur.fetchall():
        if str(product_id) not in reviews_dict:
            reviews_dict[str(product_id)] = []

        reviews_dict[str(product_id)].append({
            "user": username,
            "rating": rating,
            "comment": comment,
            "date": date,
            "modified": bool(modified),
            "editing": bool(editing)
        })

    with open(REVIEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(reviews_dict, f, indent=4, ensure_ascii=False)

    print(f"✅ {len(reviews_dict)} produits avec avis exportés → {REVIEWS_FILE}")


def export_products(conn):

    """Exporter les produits et leurs données associées en JSON."""

    cur = conn.cursor()
    products_dict = {}

    # récupérer tous les produits
    cur.execute("""
        SELECT id, name, provider, image, description_fr, description_en, reference_fr, reference_en, category, age_group, estimated_price, allow_reviews, display_price, allow_order, display_recommendations, ordonnance
        FROM products
    """)
    for product_id, name, provider, image, description_fr, description_en, reference_fr, reference_en, category, age_group, estimated_price, allow_reviews, display_price, allow_order, display_recommendations, ordonnance in cur.fetchall():
        product_info = {
            "name": name,
            "provider": provider,
            "image": image,
            "description_fr": description_fr,
            "description_en": description_en,
            "reference_fr": reference_fr,
            "reference_en": reference_en,
            "component": [],
            "tags": [],
            "category": category,
            "age_group": age_group,
            "estimated_price": estimated_price,
            "allow_reviews": bool(allow_reviews),
            "display_price": bool(display_price),
            "allow_order": bool(allow_order),
            "display_recommendations": bool(display_recommendations),
            "ordonnance": bool(ordonnance)
        }

        # composants
        cur.execute("SELECT component FROM product_components WHERE product_id = ?", (product_id,))
        for (component,) in cur.fetchall():
            product_info["component"].append(component)

        # tags
        cur.execute("SELECT tag FROM product_tags WHERE product_id = ?", (product_id,))
        for (tag,) in cur.fetchall():
            product_info["tags"].append(tag)

        products_dict[str(product_id)] = product_info

    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products_dict, f, indent=4, ensure_ascii=False)

    print(f"✅ {len(products_dict)} produits exportés → {PRODUCTS_FILE}")


def export_pharmacies(conn):

    """Exporter les données des pharmacies depuis SQLite vers JSON."""

    cur = conn.cursor()

    # Récupérer toutes les pharmacies
    cur.execute("""
        SELECT id, name, address, latitude, longitude, phone_number
        FROM pharmacies
    """)
    pharmacies_rows = cur.fetchall()

    pharmacies_data = {}

    for row in pharmacies_rows:
        pharmacy_id, name, address, latitude, longitude, phone_number = row

        # Récupérer les produits liés à cette pharmacie
        cur.execute("""
            SELECT product_id, price, qty
            FROM pharmacy_products
            WHERE pharmacy_id = ?
        """, (pharmacy_id,))
        product_rows = cur.fetchall()

        available_products = {
            str(product_id): {"price": price, "qty": qty}
            for product_id, price, qty in product_rows
        }

        # Construire le JSON pour cette pharmacie
        pharmacies_data[str(pharmacy_id)] = {
            "name": name,
            "address": address,
            "coords": [latitude, longitude],
            "available_products": available_products,
            "phone_number": phone_number,
        }

    # Sauvegarde dans un fichier
    with open(PHARMACIES_FILE, "w", encoding="utf-8") as f:
        json.dump(pharmacies_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Export terminé : {len(pharmacies_data)} pharmacies écrites dans {PHARMACIES_FILE}")


def export_product_user_interaction(conn):

    """Exporter les données d'interaction utilisateur/produit depuis SQLite vers JSON."""

    cur = conn.cursor()
    cur = conn.cursor()
    cur.execute("SELECT user_id, product_id, score FROM user_product_interactions")
    rows = cur.fetchall()

    # Construire un dict du type {user_id: {product_id: score}}
    interactions = {}
    for user_id, product_id, score in rows:
        if user_id not in interactions:
            interactions[user_id] = {}
        interactions[user_id][product_id] = score

    # Sauvegarde dans un fichier
    with open(USER_PRODUCT_FILE, "w", encoding="utf-8") as f:
        json.dump(interactions, f, indent=2, ensure_ascii=False)

    print(f"✅ Export terminé : {len(interactions)} user interactions écrites dans {USER_PRODUCT_FILE}")


def export_settings(conn):
    
    """Exporter les paramètres depuis SQLite vers JSON."""

    cur = conn.cursor()
    cur.execute("SELECT key, value FROM settings")
    rows = cur.fetchall()

    settings = {key: value for key, value in rows}

    # Sauvegarde dans un fichier
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    print(f"✅ Export terminé : {len(settings)} paramètres écrits dans {SETTINGS_FILE}")


def main():

    print("🚀 Export SQL → JSON...")
    conn = sqlite3.connect(DB_FILE)

    export_users(conn)
    export_reviews(conn)
    export_products(conn)
    export_pharmacies(conn)
    export_product_user_interaction(conn)

    conn.close()
    print("🎉 Export terminé avec succès.")


if __name__ == "__main__":
    main()

# Lancement du script : python -m data.migrate_sql_to_json