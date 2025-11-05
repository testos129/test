import sqlite3
from datetime import datetime, timedelta
from nicegui import ui
import re
from fastapi import Request

from security.passwords import hash_password
from services.items import get_total_price_for_product, get_product
from translations.translations import t

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


def get_user_info(user_id: int) -> tuple | None:

    """Retourne les informations disponibles pour un utilisateur, ou None s'il n'existe pas."""

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT username, email, password, is_delivery_person, is_admin, is_confirmed, allow_comments, confirmation_code, code_expiration_date, delivery_address FROM users WHERE id = ?", (user_id,)
        )

        row = cursor.fetchone()  # -> tuple avec les infos ou None

        if not row:
            return None  # utilisateur inexistant
        
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
            "delivery_address": row[9]
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


def update_user(user_id: int, email: str | None, password: str | None, address: str | None):

    """Met à jour l'email, le mot de passe et/ou l'adresse d'un utilisateur sans écraser les champs non fournis."""

    # Construction dynamique de la requête SQL
    fields = []
    values = []

    if email is not None:
        fields.append("email = ?")
        values.append(email)
    if password is not None:
        fields.append("password = ?")
        values.append(password)
    if address is not None:
        fields.append("delivery_address = ?")
        values.append(address)

    # Si aucun champ à mettre à jour, ne rien faire
    if not fields:
        return

    # Ajout de l'ID à la fin pour la clause WHERE
    values.append(user_id)

    query = f"UPDATE users SET {', '.join(fields)} WHERE id = ?"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(values))
        conn.commit()
    
    # """Met à jour l'email, le mot de passe et/ou l'adresse d'un utilisateur."""
    
    # with get_connection() as conn:
    #     cursor = conn.cursor()
    #     if password is None:
    #         cursor.execute(
    #             "UPDATE users SET email = ? WHERE id = ?",
    #             (email, user_id),
    #         )
    #     else:
    #         cursor.execute(
    #             "UPDATE users SET email = ?, password = ? WHERE id = ?",
    #             (email, password, user_id),
    #         )
    #     conn.commit()


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
        print(f"Erreur suppression utilisateur {user_id}: {e}")
        return False


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
def register_order(user_id: int, delivery_fee: float = 0, lat: float | None = None, lng: float | None = None, address: str | None = None):

    """
    Crée une nouvelle commande pour l'utilisateur :
    - récupère son panier
    - calcule le total pour chaque produit
    - insère chaque produit dans la table orders avec un order_id unique par commande
    """
    
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    panier = get_panier(user_id)
    if not panier:
        print("⚠️ Le panier est vide.")
        return

    with get_connection() as conn:
        cur = conn.cursor()

        # Générer un nouvel order_id unique
        cur.execute("SELECT MAX(order_id) FROM orders")
        row = cur.fetchone()
        new_order_id = (row[0] or 0) + 1

        for product_id, qty in panier.items():
            details = get_total_price_for_product(product_id, qty)['details']
            for pharma_product in details:
                pharmacy_id = pharma_product['pharmacy_id']
                total_price = pharma_product['unit_price'] * pharma_product['taken_qty']

            cur.execute("""
                INSERT INTO orders (order_id, user_id, product_id, qty, total_price, pharmacy_id, date, status, latitude, longitude, address)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (new_order_id, user_id, product_id, qty, total_price, pharmacy_id, today, "pending", lat, lng, address))
        
        if delivery_fee:
            cur.execute("""
                INSERT INTO orders (order_id, user_id, product_id, qty, total_price, date, status, latitude, longitude, address)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (new_order_id, user_id, 0, 0, delivery_fee, today, "pending", lat, lng, address))  # product_id 0 = frais de livraison

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
                SELECT product_id, qty, total_price, user_id, pharmacy_id, date, address, latitude, longitude, status
                FROM orders
                WHERE order_id = ?
            """, (order_id,))
        rows = cur.fetchall()

        if not rows:
            return None

        items = []
        total = 0.0

        for product_id, qty, total_price, user_id, pharmacy_id, date, address, latitude, longitude, status in rows:

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
            "customer": get_user_from_id(rows[0][3]),
            "date": rows[0][5],
            "address": rows[0][6],
            "lat": rows[0][7],
            "lng": rows[0][8],
            "status": rows[0][9],
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
            SELECT product_id, qty, total_price, pharmacy_id, date, address, latitude, longitude
            FROM orders
            WHERE user_id = ? AND order_id = ?
        """, (user_id, order_id))
        rows = cur.fetchall()

        if not rows:
            return None

        # Étape 3 : formater la commande
        items = []
        total = 0.0

        for product_id, qty, total_price, pharmacy_id, date, address, latitude, longitude in rows:

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
            "lat": rows[0][6],
            "lng": rows[0][7],
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
    } """

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT o.order_id, u.username, o.product_id, p.name, o.qty, o.total_price, o.date, o.latitude, o.longitude, o.address
            FROM orders o
            JOIN users u ON o.user_id = u.id
            LEFT JOIN products p ON o.product_id = p.id
            WHERE o.status = 'pending'
            ORDER BY o.date DESC
        """)
        rows = cur.fetchall()

    # Regrouper les données par order_id
    orders = {}
    for order_id, username, product_id, product_name, qty, total_price, date, lat, lng, address in rows:
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
                "address": address
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
                SELECT product_id, qty, total_price, user_id, pharmacy_id, date, address, latitude, longitude
                FROM orders
                WHERE order_id = ?
            """, (order_id,))
            rows = cur.fetchall()

            if not rows:
                continue

            items = []
            total = 0.0
            delivery_cost = 0.0

            for product_id, qty, total_price, user_id, pharmacy_id, date, address, latitude, longitude in rows:
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
                "lat": rows[0][7],
                "lng": rows[0][8],
                "delivery_cost": delivery_cost,
                "total": total + delivery_cost,
                "items": items
            })

        return orders
    

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
                SELECT product_id, qty, total_price, delivery_person_id, pharmacy_id, date, address, latitude, longitude
                FROM orders
                WHERE order_id = ?
            """, (order_id,))
            rows = cur.fetchall()

            if not rows:
                continue

            items = []
            total = 0.0
            delivery_cost = 0.0

            for product_id, qty, total_price, delivery_person_id, pharmacy_id, date, address, latitude, longitude in rows:
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
                "lat": rows[0][7],
                "lng": rows[0][8],
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