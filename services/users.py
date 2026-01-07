import sqlite3
from datetime import datetime, timedelta
from nicegui import ui
import re
from fastapi import Request
import math
import random
import string

from security.passwords import hash_password
from services.items import get_total_price_for_product, get_product
from services.logging_setup import get_logger
from translations.translations import t

from services.file_io import load_yaml
functionalities_switch = load_yaml('components/functionalities_switch.yaml')
ENABLE_USE_STOCK_MODE = functionalities_switch.get('ENABLE_USE_STOCK_MODE', True)

logger = get_logger('default')


DB_PATH = "data/data.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


# === Gestion des utilisateurs ===
def get_id_from_username(username: str) -> int | None:

    """Retourne l'ID d'un utilisateur à partir de son username."""

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()

        return row[0] if row else None


def get_user_from_id(user_id: int) -> str | None:

    """Renvoie le username à partir de l'id de l'utilisateur, ou None si introuvable."""

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()

        return row[0] if row else None


def get_user_info(user_id: int) -> dict | None:

    """Retourne toutes les informations disponibles pour un utilisateur, ou None s'il n'existe pas."""

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                username, email, password,
                is_delivery_person, is_admin, is_confirmed, allow_comments,
                confirmation_code, code_expiration_date,
                phone_number,
                main_address_street, main_address_city, main_address_postal_code, main_address_details,
                secondary_address_street, secondary_address_city, secondary_address_postal_code, secondary_address_details,
                current_lat, current_lng, current_coords_date
            FROM users
            WHERE id = ?
        """, (user_id,))

        row = cursor.fetchone()

        if not row:
            return None

        user = {
            "username": row[0],
            "email": row[1],
            "password": row[2],
            "is_delivery_person": bool(row[3]),
            "is_admin": bool(row[4]),
            "is_confirmed": bool(row[5]),
            "allow_comments": bool(row[6]),
            "confirmation_code": row[7],
            "code_expiration_date": row[8],
            "phone_number": row[9],
            "main_address_street": row[10],
            "main_address_city": row[11],
            "main_address_postal_code": row[12],
            "main_address_details": row[13],
            "secondary_address_street": row[14],
            "secondary_address_city": row[15],
            "secondary_address_postal_code": row[16],
            "secondary_address_details": row[17],
            "current_lat": row[18],
            "current_lng": row[19],
            "current_coords_date": row[20]
        }

        return user


def add_user(username: str, password: str, email: str) -> list[bool, bool]:

    """Ajoute un utilisateur dans la DB. 
    Le premier élement de la liste de retour concerne le username (déjà existant ou non) et le second concerne l'email
    
    Le premier utilisateur créé est automatiquement admin."""

    res = [True, True]
    with get_connection() as conn:
        cursor = conn.cursor()

        # Vérifier si l’utilisateur existe déjà
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            res[0] = False

        # Vérifier si l'email existe déjà
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            res[1] = False

        # Créer l’utilisateur
        if res[0] and res[1]:
            pwd_hash = hash_password(password)

            # Vérifier si la table users est vide
            cursor.execute("SELECT COUNT(*) FROM users")
            count = cursor.fetchone()[0]

            if count == 0:
                # Premier utilisateur → admin
                cursor.execute(
                    "INSERT INTO users (username, password, email, is_admin) VALUES (?, ?, ?, 1)",
                    (username, pwd_hash, email),
                )
            else:
                # Utilisateur normal
                cursor.execute(
                    "INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
                    (username, pwd_hash, email),
                )

            conn.commit()

    return res


def confirm_user(user_id: int):

    """Confirme un utilisateur en mettant à jour son statut is_confirmed."""

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET is_confirmed = 1, confirmation_code = NULL, code_expiration_date = NULL WHERE id = ?",
            (user_id,),
        )
        conn.commit()


def add_code_user(user_id: int, code: str):

    """
    Ajoute un code de confirmation pour un utilisateur donné,
    avec une date d'expiration fixée à 15 minutes.
    """

    # === Génération d’un code aléatoire sécurisé (6 chiffres) ===

    # === Calcul de la date d’expiration ===
    expiration_date = datetime.now() + timedelta(minutes=15)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE users
            SET confirmation_code = ?, code_expiration_date = ?
            WHERE id = ?
            """,
            (code, expiration_date, user_id),
        )
        conn.commit()


def verify_user_code(user_id: int, code: str) -> bool:

    """
    Vérifie si le code de confirmation d'un utilisateur est correct et non expiré.
    Retourne True si valide, False sinon.
    """

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT confirmation_code, code_expiration_date
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()

        # === Cas : utilisateur introuvable ou sans code ===
        if not row or not row[0]:
            return False

        stored_code = str(row[0])
        expiration_date = row[1]

        # === Vérifie si le code correspond ===
        if stored_code != str(code):
            return False

        # === Vérifie si le code n’a pas expiré ===
        if expiration_date is None or datetime.now() > datetime.fromisoformat(expiration_date):
            return False

        # === Si tout est bon ===
        return True


def update_user(
    user_id: int,
    email: str | None = None,
    password: str | None = None,
    phone_number: str | None = None,
    main_address_street: str | None = None,
    main_address_city: str | None = None,
    main_address_postal_code: str | None = None,
    main_address_details: str | None = None,
    secondary_address_street: str | None = None,
    secondary_address_city: str | None = None,
    secondary_address_postal_code: str | None = None,
    secondary_address_details: str | None = None
):
    """Met à jour l'utilisateur avec tous les nouveaux champs sans écraser ceux non fournis."""
    
    fields = []
    values = []

    # Ajout dynamique des champs
    if email is not None:
        fields.append("email = ?")
        values.append(email)
    if password is not None:
        fields.append("password = ?")
        values.append(password)
    if phone_number is not None:
        fields.append("phone_number = ?")
        values.append(phone_number)
    if main_address_street is not None:
        fields.append("main_address_street = ?")
        values.append(main_address_street)
    if main_address_city is not None:
        fields.append("main_address_city = ?")
        values.append(main_address_city)
    if main_address_postal_code is not None:
        fields.append("main_address_postal_code = ?")
        values.append(main_address_postal_code)
    if main_address_details is not None:
        fields.append("main_address_details = ?")
        values.append(main_address_details)
    if secondary_address_street is not None:
        fields.append("secondary_address_street = ?")
        values.append(secondary_address_street)
    if secondary_address_city is not None:
        fields.append("secondary_address_city = ?")
        values.append(secondary_address_city)
    if secondary_address_postal_code is not None:
        fields.append("secondary_address_postal_code = ?")
        values.append(secondary_address_postal_code)
    if secondary_address_details is not None:
        fields.append("secondary_address_details = ?")
        values.append(secondary_address_details)

    # Si rien à mettre à jour, on quitte
    if not fields:
        return

    # Ajout de l'ID pour WHERE
    values.append(user_id)
    query = f"UPDATE users SET {', '.join(fields)} WHERE id = ?"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, values)
        conn.commit()


def delete_user(user_id: int) -> bool:

    """
    Supprime un utilisateur et toutes ses données liées dans les autres tables.
    Ne supprime pas les admins.
    """

    try:
        with get_connection() as conn:
            cur = conn.cursor()

            # Vérifier si l'utilisateur est admin
            cur.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
            row = cur.fetchone()
            if not row:
                return False  # utilisateur introuvable
            if row[0] == 1:
                print(f"Tentative de suppression d'un admin (id={user_id}), refusée.")
                return False

            # Supprimer dans les tables liées
            tables_with_user_id = [
                "reviews",
                "user_history",
                "panier",
                "wallet_history",
                "wallets",
                "orders",
                "user_product_interactions"
            ]
            for table in tables_with_user_id:
                cur.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))

            # Enfin supprimer l'utilisateur
            cur.execute("DELETE FROM users WHERE id = ?", (user_id,))

            conn.commit()
            return True
    except Exception as e:
        logger.warning(f"Fail to delete user {user_id}: {e}")
        return False


def update_user_coordinates(user_id: int, user_lat: float, user_lng: float):

    """Met à jour les coordonnées de l'utilisateur dans la table users."""
    
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            UPDATE users
            SET 
                current_lat = ?,
                current_lng = ?,
                current_coords_date = ?
            WHERE id = ?
        """, (
            user_lat,
            user_lng,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            user_id
        ))

        conn.commit()


def get_delivery_person_list_for_customer(user_id: int):

    """Retourne la liste des livreurs disponibles pour un client."""

    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT DISTINCT delivery_person_id
            FROM orders
            WHERE user_id = ?
            AND status IN ('in_progress')
            AND delivery_person_id IS NOT NULL
        """, (user_id,))

        results = cur.fetchall()

        delivery_ids = [row[0] for row in results]

        return delivery_ids


# === Gestion des  visites ===
def record_visit(user_id: int, page_path: str):

    """Incrémente le compteur de visites pour une page donnée."""

    display_page = get_display_page(page_path)

    with get_connection() as conn:
        cursor = conn.cursor()

        # Vérifier si une ligne existe déjà pour ce user et cette page brute
        cursor.execute(
            "SELECT visits FROM user_history WHERE user_id = ? AND page = ?",
            (user_id, page_path),
        )
        row = cursor.fetchone()

        if row:
            # Incrémenter simplement le compteur
            cursor.execute(
                "UPDATE user_history SET visits = visits + 1 WHERE user_id = ? AND page = ?",
                (user_id, page_path),
            )
        else:
            # Insère une nouvelle ligne avec page brute + display page
            cursor.execute(
                "INSERT INTO user_history (user_id, page, display_page, visits) VALUES (?, ?, ?, ?)",
                (user_id, page_path, display_page, 1),
            )

        conn.commit()


def get_visit_history(user_id: int):

    """Retourne l'historique des visites (page -> (display_page, nombre de visites)) d'un utilisateur."""

    with get_connection() as conn:
        cursor = conn.cursor()

        # Récupérer l'historique
        cursor.execute(
            "SELECT page, display_page, visits FROM user_history WHERE user_id = ?", (user_id,)
        )

        return {page: (display_page, count) for page, display_page, count in cursor.fetchall()}
    

def get_display_page(page: str):

    """Retourne le nom de la page à partir d'un chemin"""

    pattern = r"^/product/(\d+)(/.*|\?.*)?$"

    match = re.match(pattern, page)
    
    if match:
        product_id = match.group(1)
        suffix = match.group(2) if match.group(2) else ""

        product_name = get_product(product_id)['name']

        return "product " + product_name + suffix.replace('/', ' ')
    
    else:
        return page.replace('/', '')


# === Gestion du panier ===
def add_panier_item(user_id: int, product_id: str, request: Request, allow_duplicates=False) -> bool:

    """Ajoute un produit au panier (avec option doublons)."""

    lang_cookie = request.cookies.get("language", "fr")

    with get_connection() as conn:
        cursor = conn.cursor()

        if not allow_duplicates:
            cursor.execute(
                "SELECT 1 FROM panier WHERE user_id = ? AND product_id = ?",
                (user_id, product_id),
            )
            if cursor.fetchone():
                ui.notify(t("product_already_in_panier", lang_cookie))
                return False

        cursor.execute("""
            INSERT INTO panier (user_id, product_id, quantity)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, product_id)
            DO UPDATE SET quantity = panier.quantity + 1;
        """, (user_id, product_id))
        conn.commit()

    # Rechargement de l'ui pour mettre à jour l'affichage du panier
    ui.notify(t("product_added_panier", lang_cookie), color="positive")
    ui.navigate.reload()

    return True


def remove_panier_item(user_id: int, product_id: str, request: Request, remove_all=False):

    """Retire un produit du panier."""

    lang_cookie = request.cookies.get("language", "fr")

    with get_connection() as conn:
        cursor = conn.cursor()

        if remove_all:
            cursor.execute(
                "DELETE FROM panier WHERE user_id = ? AND product_id = ?",
                (user_id, product_id),
            )
        else:
            # Vérifier la quantité actuelle
            cursor.execute(
                "SELECT quantity FROM panier WHERE user_id = ? AND product_id = ?",
                (user_id, product_id),
            )
            row = cursor.fetchone()

            if row:
                current_qty = row[0]
                if current_qty > 1:
                    # Décrémente la quantité
                    cursor.execute(
                        "UPDATE panier SET quantity = quantity - 1 WHERE user_id = ? AND product_id = ?",
                        (user_id, product_id),
                    )
                else:
                    # Si quantité = 1 → suppression
                    cursor.execute(
                        "DELETE FROM panier WHERE user_id = ? AND product_id = ?",
                        (user_id, product_id),
                    )

        if cursor.rowcount == 0:
            ui.notify(t("product_not_in_panier", lang_cookie))
        else:
            conn.commit()
            # Rechargement de l'ui pour mettre à jour l'affichage du panier
            ui.navigate.reload()


def get_panier(user_id: int):

    """
    Retourne le panier d'un utilisateur sous forme de dict {product_id: quantity}.
    Exemple : {1: 2, 2: 1} -> produit 1 en 2 exemplaires, produit 2 en 1 exemplaire
    """

    with get_connection() as conn:
        cursor = conn.cursor()

        # Récupération des produits + quantités
        cursor.execute("""
            SELECT product_id, quantity
            FROM panier
            WHERE user_id = ?
        """, (user_id,))
        
        return {r[0]: r[1] for r in cursor.fetchall()}
    

def get_len_panier(user_id: int) -> int:

    """
    Retourne le nombre total d'articles dans le panier d'un utilisateur
    (somme des quantités).
    Exemple : {1: 2, 2: 1} -> 3
    """
    
    with get_connection() as conn:
        cursor = conn.cursor()

        # Calcul du total directement en SQL
        cursor.execute("""
            SELECT SUM(quantity)
            FROM panier
            WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()

        return row[0] or 0


def delete_panier(user_id: int):

    """Vide complètement le panier de l'utilisateur (tous les produits)."""

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("DELETE FROM panier WHERE user_id = ?", (user_id,))
        conn.commit()


# === Gestion du wallet ===
def get_wallet_balance(user_id: int) -> float:

    """Retourne le solde du wallet d'un utilisateur."""

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT balance FROM wallets WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

        return row[0] if row else 0.0


def add_wallet_balance(user_id: int, amount: float, request: Request, is_expense: bool = False):

    """Ajoute ou retire de l'argent du wallet d'un utilisateur."""

    # Arrondis du montant au centime
    amount = math.floor(amount * 100) / 100

    lang_cookie = request.cookies.get("language", "fr")

    with get_connection() as conn:
        cursor = conn.cursor()

        current_balance = get_wallet_balance(user_id)
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if is_expense:
            if current_balance < amount:
                ui.notify(t("insufficient_balance_2", lang_cookie), color="negative")
                return
            new_balance = current_balance - amount
            cursor.execute(
                "INSERT INTO wallet_history (user_id, date, amount, description) VALUES (?, ?, ?, ?)",
                (user_id, today, -amount, "Dépense"),
            )
        else:
            new_balance = current_balance + amount
            cursor.execute(
                "INSERT INTO wallet_history (user_id, date, amount, description) VALUES (?, ?, ?, ?)",
                (user_id, today, amount, "Recharge"),
            )

        # Mettre à jour ou insérer le solde
        cursor.execute(
            "INSERT INTO wallets (user_id, balance) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET balance = ?",
            (user_id, new_balance, new_balance),
        )

        conn.commit()


def get_wallet_history(user_id: int):

    """Retourne l'historique des transactions du wallet d'un utilisateur."""

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT date, amount, description FROM wallet_history WHERE user_id = ? ORDER BY date DESC",
            (user_id,),
        )

        return cursor.fetchall()
    

# === Gestion des commandes ===
def generate_order_code(length=5):

    """Génère un code alphanumérique pour confirmation de la commande"""

    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def register_order(user_id: int, 
                   delivery_fee: float = 0, 
                   lat: float | None = None, 
                   lng: float | None = None, 
                   address: str | None = None,
                   address_details: str | None = None,
                   pharmacy_id: str | None = None):

    """
    Crée une nouvelle commande pour l'utilisateur :
    - récupère son panier
    - calcule le total pour chaque produit
    - insère chaque produit dans la table orders avec un order_id unique par commande
    """
    
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    panier = get_panier(user_id)
    if not panier:
        return
    
    if not ENABLE_USE_STOCK_MODE and not pharmacy_id:
        return
    
    order_code = generate_order_code()

    with get_connection() as conn:
        cur = conn.cursor()

        # Générer un nouvel order_id unique
        cur.execute("SELECT MAX(order_id) FROM orders")
        row = cur.fetchone()
        new_order_id = (row[0] or 0) + 1

        for product_id, qty in panier.items():
            if ENABLE_USE_STOCK_MODE:
                details = get_total_price_for_product(product_id, qty)['details']
                for pharma_product in details:
                    pharmacy_id = pharma_product['pharmacy_id']
                    total_price = pharma_product['unit_price'] * pharma_product['taken_qty']

                    cur.execute("""
                        INSERT INTO orders (
                                order_id, user_id, product_id, qty, total_price, pharmacy_id, date, 
                                status, latitude, longitude, address, address_details, order_code
                            )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (new_order_id, user_id, product_id, qty, total_price, pharmacy_id, today, "pending", lat, lng, address, address_details, order_code))
            
            else:
                estimated_price = get_product(product_id)['estimated_price']
                if estimated_price:
                    total_price = estimated_price * qty
                else:
                    total_price = 0  # cas où pas d'estimation de prix

                cur.execute("""
                    INSERT INTO orders (
                            order_id, user_id, product_id, qty, total_price, pharmacy_id, date, 
                            status, latitude, longitude, address, address_details, order_code
                        )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (new_order_id, user_id, product_id, qty, total_price, pharmacy_id, today, "pending", lat, lng, address, address_details, order_code))
        
        if delivery_fee:
            cur.execute("""
                INSERT INTO orders (
                        order_id, user_id, product_id, qty, total_price, date, 
                        status, latitude, longitude, address, address_details, order_code
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (new_order_id, user_id, 0, 0, delivery_fee, today, "pending", lat, lng, address, address_details, order_code))  # product_id 0 = frais de livraison

        conn.commit()


def get_order_history(user_id: int):

    """Récupère les commandes passées par un utilisateur sous forme {order_id: (date, total_amount, items)}, incluant les frais de livraison."""

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                o.order_id,
                o.date,
                SUM(o.total_price) AS total_amount,
                GROUP_CONCAT(
                    CASE 
                        WHEN o.product_id = 0 THEN 'Frais de livraison'
                        ELSE p.name || ' x' || o.qty
                    END,
                    ', '
                ) AS items
            FROM orders o
            LEFT JOIN products p ON o.product_id = p.id
            WHERE o.user_id = ?
            GROUP BY o.order_id, o.date
            ORDER BY o.date DESC
        """, (user_id,))

        return cur.fetchall()

        

def get_order_details(order_id: int):

    """Récupère les détails d'une commande spécifique."""

    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
                SELECT product_id, qty, total_price, user_id, pharmacy_id, date, address, address_details, latitude, longitude, status, delivery_person_id, order_code, close_date, user_notified
                FROM orders
                WHERE order_id = ?
            """, (order_id,))
        rows = cur.fetchall()

        if not rows:
            return None

        items = []
        total = 0.0

        for product_id, qty, total_price, user_id, pharmacy_id, date, address, address_details, latitude, longitude, status, delivery_person_id, order_code, close_date, user_notified in rows:

            if product_id != 0:
                product = get_product(product_id)
                items.append({
                    "product_id": product_id,
                    "pharmacy_id": pharmacy_id,
                    "name": product.get("name", "Inconnu") if product else "Inconnu",
                    "qty": qty,
                    "price": total_price / qty if qty > 0 else total_price
                })
                total += total_price
            else:  # product id 0 = frais de livraison
                delivery_cost = total_price

        return {
            "order_id": order_id,
            "user_id": rows[0][3],
            "customer": get_user_from_id(rows[0][3]),
            "date": rows[0][5],
            "address": rows[0][6],
            "address_details": rows[0][7],
            "lat": rows[0][8],
            "lng": rows[0][9],
            "status": rows[0][10],
            "delivery_person_id": rows[0][11],
            "order_code": rows[0][12],
            "close_date": rows[0][13],
            "user_notified": rows[0][14],
            "delivery_cost": delivery_cost,
            "total": total + delivery_cost,
            "items": items
        }
        

def get_last_order(user_id: int):

    """Récupère la dernière commande complète d'un utilisateur."""

    with get_connection() as conn:
        cur = conn.cursor()

        # Étape 1 : trouver le dernier order_id de l'utilisateur
        cur.execute("""
            SELECT order_id, MAX(date)
            FROM orders
            WHERE user_id = ?
        """, (user_id,))
        last_order = cur.fetchone()

        if not last_order or not last_order[0]:
            return None  # aucun historique de commande

        order_id = last_order[0]

        # Étape 2 : récupérer les détails de la commande
        cur.execute("""
            SELECT product_id, qty, total_price, pharmacy_id, date, address, address_details, latitude, longitude
            FROM orders
            WHERE user_id = ? AND order_id = ?
        """, (user_id, order_id))
        rows = cur.fetchall()

        if not rows:
            return None

        # Étape 3 : formater la commande
        items = []
        total = 0.0

        for product_id, qty, total_price, pharmacy_id, date, address, address_details, latitude, longitude in rows:

            if product_id != 0:
                product = get_product(product_id)
                items.append({
                    "product_id": product_id,
                    "pharmacy_id": pharmacy_id,
                    "name": product.get("name", "Inconnu") if product else "Inconnu",
                    "qty": qty,
                    "price": total_price / qty if qty > 0 else total_price
                })
                total += total_price
            else:  # product id 0 = frais de livraison
                delivery_cost = total_price

        return {
            "order_id": order_id,
            "date": rows[0][4],
            "address": rows[0][5],
            "address_details": rows[0][6],
            "lat": rows[0][7],
            "lng": rows[0][8],
            "delivery_cost": delivery_cost,
            "total": total + delivery_cost,
            "items": items
        }
    

def get_all_pending_order():
    
    """ Récupère toutes les commandes en attente de tous les utilisateurs en commençant par les plus récents.
    Inclut aussi les frais de livraison (product_id = 0) dans le total.

    Renvoie une liste de dictionnaires :
    {
        "id": order_id,
        "customer": username,
        "items": {item_1: qty_1, item_2: qty_2, ...},
        "total": total_price,
        "date": date,
        "lat": latitude (optionnel),
        "lng": longitude (optionnel),
        "address": address (optionnel)
        "address_details": address_details (optionnel)
    } """

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT o.order_id, u.username, o.product_id, p.name, o.qty, o.total_price, o.date, o.latitude, o.longitude, o.address, o.address_details
            FROM orders o
            JOIN users u ON o.user_id = u.id
            LEFT JOIN products p ON o.product_id = p.id
            WHERE o.status = 'pending'
            ORDER BY o.date DESC
        """)
        rows = cur.fetchall()

    # Regrouper les données par order_id
    orders = {}
    for order_id, username, product_id, product_name, qty, total_price, date, lat, lng, address, address_details in rows:
        if order_id not in orders:
            orders[order_id] = {
                "id": order_id,
                "customer": username,
                "items": {},
                "total": 0.0,
                "delivery_cost": 0.0,
                "date": date,
                "lat": lat,
                "lng": lng,
                "address": address,
                "address_details": address_details
            }

        # Si product_id = 0 → frais de livraison donc pas ajouter dans la liste des produits
        if product_id != 0:
            if product_name in orders[order_id]["items"]:
                orders[order_id]["items"][product_name] += qty
            else:
                orders[order_id]["items"][product_name] = qty
        else:
            orders[order_id]["delivery_cost"] += total_price or 0.0

        # Ajouter le coût total (inclut les frais de livraison)
        orders[order_id]["total"] += total_price or 0.0

    return list(orders.values())


def take_order(order_id: int, delivery_person_id: int, max_order: int) -> bool:

    """ Marque une commande comme prise en charge par un livreur si le livreur n'a pas atteint la max de livraison en cours. """

    with get_connection() as conn:
        cur = conn.cursor()

       # Vérifier combien de commandes en cours le livreur a déjà
        cur.execute("""
            SELECT COUNT(DISTINCT order_id)
            FROM orders
            WHERE delivery_person_id = ? AND status = 'in_progress'
        """, (delivery_person_id,))
        current_orders = cur.fetchone()[0]

        if current_orders >= max_order:

            return False  # Trop de commandes déjà prises

        # Verifier que la commande est toujours en attente
        cur.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,))
        row = cur.fetchone()
        if not row or row[0] != 'pending':

            return False  # commande introuvable ou déjà prise

        # Mettre à jour le statut de toutes les lignes de la commande
        cur.execute("""
            UPDATE orders
            SET status = 'in_progress',
                delivery_person_id = ?
            WHERE order_id = ? AND status = 'pending'
        """, (delivery_person_id, order_id))
        conn.commit()

        return True
    

def get_orders_for_delivery_person(delivery_person_id: int, status: str='in_progress'):

    """Récupère toutes les commandes en cours pour un livreur donné et un status donné."""

    with get_connection() as conn:
        cur = conn.cursor()

        # Sélection des commandes correspondantes
        cur.execute("""
            SELECT DISTINCT order_id
            FROM orders
            WHERE status = ?
              AND delivery_person_id = ?
            ORDER BY date DESC
        """, (status, delivery_person_id,))
        order_rows = cur.fetchall()

        if not order_rows:
            return []

        orders = []

        # Pour chaque commande trouvée, on récupère ses détails complets
        for (order_id,) in order_rows:
            cur.execute("""
                SELECT product_id, qty, total_price, user_id, pharmacy_id, date, address, address_details, latitude, longitude
                FROM orders
                WHERE order_id = ?
            """, (order_id,))
            rows = cur.fetchall()

            if not rows:
                continue

            items = []
            total = 0.0
            delivery_cost = 0.0

            for product_id, qty, total_price, user_id, pharmacy_id, date, address, address_details, latitude, longitude in rows:
                if product_id != 0:
                    product = get_product(product_id)
                    items.append({
                        "product_id": product_id,
                        "pharmacy_id": pharmacy_id,
                        "name": product.get("name", "Inconnu") if product else "Inconnu",
                        "qty": qty,
                        "price": total_price / qty if qty > 0 else total_price
                    })
                    total += total_price
                else:
                    delivery_cost = total_price

            orders.append({
                "order_id": order_id,
                "customer": get_user_from_id(rows[0][3]),
                "date": rows[0][5],
                "address": rows[0][6],
                "address_details": rows[0][7],
                "lat": rows[0][8],
                "lng": rows[0][9],
                "delivery_cost": delivery_cost,
                "total": total + delivery_cost,
                "items": items
            })

        return orders
    

def get_order_code(order_id: int):

    """Récupère le code de confirmation pour une commande donnée (une seule valeur)."""

    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT order_code
            FROM orders
            WHERE order_id = ?
            LIMIT 1
        """, (order_id,))

        row = cur.fetchone()

        if row is None:
            return None
        
        return row[0]


def get_orders_for_customer(user_id: int, status: str='in_progress'):

    """Récupère toutes les commandes en cours pour un utilisateur donné et un status donné."""

    with get_connection() as conn:
        cur = conn.cursor()

        # Sélection des commandes correspondantes
        cur.execute("""
            SELECT DISTINCT order_id
            FROM orders
            WHERE status = ?
              AND user_id = ?
            ORDER BY date DESC
        """, (status, user_id,))
        order_rows = cur.fetchall()

        if not order_rows:
            return []

        orders = []

        # Pour chaque commande trouvée, on récupère ses détails complets
        for (order_id,) in order_rows:
            cur.execute("""
                SELECT product_id, qty, total_price, delivery_person_id, pharmacy_id, date, address, address_details, latitude, longitude, order_code, close_date, user_notified
                FROM orders
                WHERE order_id = ?
            """, (order_id,))
            rows = cur.fetchall()

            if not rows:
                continue

            items = []
            total = 0.0
            delivery_cost = 0.0

            for product_id, qty, total_price, delivery_person_id, pharmacy_id, date, address, address_details, latitude, longitude, order_code, close_date, user_notified in rows:
                if product_id != 0:
                    product = get_product(product_id)
                    items.append({
                        "product_id": product_id,
                        "pharmacy_id": pharmacy_id,
                        "name": product.get("name", "Inconnu") if product else "Inconnu",
                        "qty": qty,
                        "price": total_price / qty if qty > 0 else total_price
                    })
                    total += total_price
                else:
                    delivery_cost = total_price

            orders.append({
                "order_id": order_id,
                "delivery_person": get_user_from_id(rows[0][3]),
                "date": rows[0][5],
                "address": rows[0][6],
                "address_details": rows[0][7],
                "lat": rows[0][8],
                "lng": rows[0][9],
                "order_code": rows[0][10],
                "close_date": rows[0][11],
                "user_notified": rows[0][12],
                "delivery_cost": delivery_cost,
                "total": total + delivery_cost,
                "items": items
            })

        return orders
    

def cancel_order_delivery(order_id: int) -> bool:

    """ Annule la livraison d'une commande en cours. """

    with get_connection() as conn:
        cur = conn.cursor()

        # Vérifier que la commande est en cours de livraison
        cur.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,))
        row = cur.fetchone()
        if not row or row[0] != 'in_progress':

            return False  # commande introuvable ou pas en cours

        # Remettre le statut à 'pending' et retirer le livreur assigné
        cur.execute("""
            UPDATE orders
            SET status = 'pending',
                delivery_person_id = NULL
            WHERE order_id = ? AND status = 'in_progress'
        """, (order_id,))
        conn.commit()

        return True
    

def get_in_progress_orders_count(user_id: int) -> int:

    """Retourne le nombre de commandes 'in_progress' ou 'pending' pour un utilisateur."""
    
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(DISTINCT order_id)
            FROM orders
            WHERE user_id = ? AND status IN ('in_progress', 'pending')
        """, (user_id,))
        return cur.fetchone()[0] or 0
    

def verify_order_code(order_code_input: str, oid: int) -> bool:

    """Vérifie si le code donné correspond à celui enregistré pour la commande."""

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT order_code FROM orders
            WHERE order_id = ?
            LIMIT 1
        """, (oid,))

        row = cur.fetchone()

        if not row:
            # Aucune commande trouvée
            return False

        stored_code = row[0]

        # Pas de code renvoie True car dans ce cas pas de vérification du code
        if stored_code is None:
            return True
        
        return stored_code.strip() == order_code_input.strip()
    

def close_order(oid: int) -> bool:

    """Passe une commande du statut 'in_progress' à 'completed' si possible."""

    with get_connection() as conn:
        cur = conn.cursor()

        # Vérifier le statut actuel
        cur.execute("""
            SELECT status FROM orders
            WHERE order_id = ?
            LIMIT 1
        """, (oid,))

        row = cur.fetchone()

        if not row:
            # commande inexistante
            return False

        status = row[0]

        if status != "in_progress":
            # On ne peut clôturer que les commandes en cours
            return False

        # Mise à jour du statut
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute("""
            UPDATE orders
            SET status = 'completed',
                close_date = ?
            WHERE order_id = ?
        """, (now, oid))

        conn.commit()

        return True


def credit_delivery_person(user_id: int, oid: int) -> bool:

    """
    Vérifie que le user est un livreur, récupère les frais de livraison (product_id = 0)
    puis crédite le wallet du livreur de (frais / 2).
    """

    with get_connection() as conn:
        cur = conn.cursor()

        # === Vérifier que l'utilisateur est un livreur ===
        cur.execute("""
            SELECT is_delivery_person FROM users
            WHERE id = ?
        """, (user_id,))
        row = cur.fetchone()

        if not row:
            return False  # l'utilisateur n'existe pas

        role = row[0]

        if not role:
            return False  # pas un livreur


        # === Récupérer les frais de livraison = ligne product_id = 0 ===
        cur.execute("""
            SELECT total_price FROM orders
            WHERE order_id = ? AND product_id = 0
            LIMIT 1
        """, (oid,))
        row = cur.fetchone()

        if not row:
            return False  # aucune ligne de frais trouvée

        delivery_fee = row[0]
        credit_amount = delivery_fee / 2


        # === Vérifier si le livreur a déjà reçu le crédit (éviter double crédit) ===
        cur.execute("""
            SELECT credited FROM orders
            WHERE order_id = ? AND product_id = 0
        """, (oid,))
        row = cur.fetchone()

        already_credited = row[0]

        if already_credited == 1:
            return False  # déjà payé


        # === Vérifier si un wallet existe, sinon le créer ===
        cur.execute("SELECT balance FROM wallets WHERE user_id = ?", (user_id,))
        wallet = cur.fetchone()

        if wallet is None:
            # créer un wallet vide
            cur.execute("""
                INSERT INTO wallets (user_id, balance)
                VALUES (?, 0)
            """, (user_id,))
            current_balance = 0
        else:
            current_balance = wallet[0]


        # === Créditer le wallet ===
        new_balance = current_balance + credit_amount

        cur.execute("""
            UPDATE wallets
            SET balance = ?
            WHERE user_id = ?
        """, (new_balance, user_id))

        # === Ajouter une entrée dans l'historique du wallet ===
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute("""
            INSERT INTO wallet_history (user_id, date, amount, description)
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            now,
            credit_amount,
            f"Crédit livraison (commande #{oid})"
        ))

        # === Marque les frais comme crédités ===
        cur.execute("""
            UPDATE orders
            SET credited = 1
            WHERE order_id = ?
        """, (oid,))

        conn.commit()

        return True
    

def get_orders_grouped_by_status():

        """
        Récupère toutes les commandes de la base de données,
        et les regroupe par statut : pending, in_progress, completed.
        
        Returns:
            dict: {
                "pending": [...],
                "in_progress": [...],
                "completed": [...]
            }
        """

        pending_orders = []
        in_progress_orders = []
        completed_orders = []

        with get_connection() as conn:
            cur = conn.cursor()

            # Sélection des commandes correspondantes
            cur.execute("""
                SELECT DISTINCT order_id
                FROM orders
                ORDER BY date DESC
            """)
            order_rows = cur.fetchall()

            if not order_rows:
                return [], [], []

            # Pour chaque commande trouvée, on récupère ses détails complets
            for (order_id,) in order_rows:
                cur.execute("""
                    SELECT product_id, qty, total_price, user_id, pharmacy_id, status, date, address, address_details, latitude, longitude, delivery_person_id, close_date
                    FROM orders
                    WHERE order_id = ?
                """, (order_id,))
                rows = cur.fetchall()

                if not rows:
                    continue

                items = []
                total = 0.0
                delivery_cost = 0.0

                for product_id, qty, total_price, user_id, pharmacy_id, status, date, address, address_details, latitude, longitude, delivery_person_id, close_date in rows:
                    if product_id != 0:
                        product = get_product(product_id)
                        items.append({
                            "product_id": product_id,
                            "pharmacy_id": pharmacy_id,
                            "name": product.get("name", "Inconnu") if product else "Inconnu",
                            "qty": qty,
                            "price": total_price / qty if qty > 0 else total_price
                        })
                        total += total_price
                    else:
                        delivery_cost = total_price

                order = {
                    "order_id": order_id,
                    "customer": get_user_from_id(rows[0][3]),
                    "status": rows[0][5],
                    "date": rows[0][6],
                    "address": rows[0][7],
                    "address_details": rows[0][8],
                    "lat": rows[0][9],
                    "lng": rows[0][10],
                    "delivery_person": get_user_from_id(rows[0][11]),
                    "close_date": rows[0][12],
                    "delivery_cost": delivery_cost,
                    "total": total + delivery_cost,
                    "items": items
                }

                if order["status"] == "pending":
                    pending_orders.append(order)
                elif order["status"] == "in_progress":
                    in_progress_orders.append(order)
                elif order["status"] == "completed":
                    completed_orders.append(order)

            return {
                "pending": pending_orders,
                "in_progress": in_progress_orders,
                "completed": completed_orders
            }


def has_unnotified_completed_order(user_id: int) -> bool:
    
    """Vérifie si un utilisateur a des commandes completed non notifiées."""

    with get_connection() as conn:
        cur = conn.cursor()
    
        cur.execute("""
            SELECT 1
            FROM orders
            WHERE user_id = ?
            AND status = 'completed'
            AND user_notified = 0
            LIMIT 1
        """, (user_id,))
        
        result = cur.fetchone()
    
    return result is not None


def mark_completed_orders_as_notified(user_id: int):

    """Marque toutes les commandes 'completed' d'un utilisateur comme notifiées."""

    with get_connection() as conn:
        cur = conn.cursor()
    
        cur.execute("""
            UPDATE orders
            SET user_notified = 1
            WHERE user_id = ?
            AND status = 'completed'
            AND user_notified = 0
        """, (user_id,))
        
        conn.commit()