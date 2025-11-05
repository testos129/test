import sqlite3
from rapidfuzz import fuzz

from services.file_io import load_json

DB_PATH = "data/data.db"

def get_connection():
    return sqlite3.connect(DB_PATH)


# === Gestion des produits ===
def get_product(product_id: int) -> dict | None:

    """Récupérer un produit (et ses composants/tags) depuis la base SQLite."""

    with get_connection() as conn:
        cursor = conn.cursor()

        # === Table Produit principale ===
        cursor.execute("""
            SELECT id, name, provider, image, description, reference, category, age_group, allow_reviews, display_price, allow_order, display_recommendations, ordonnance
            FROM products
            WHERE id = ?
        """, (product_id,))
        row = cursor.fetchone()

        if not row:
            return None  # produit inexistant

        product = {
            "id": row[0], 
            "name": row[1],
            "provider": row[2],
            "image": row[3],
            "description": row[4],
            "reference": row[5],
            "component": [],
            "tags": [],
            "category": row[6],
            "age_group": row[7],
            "allow_reviews": bool(row[8]),
            "display_price": bool(row[9]),
            "allow_order": bool(row[10]),
            "display_recommendations": bool(row[11]),
            "ordonnance": bool(row[12])
        }

        # === Récupérer les composants ===
        cursor.execute("SELECT component FROM product_components WHERE product_id = ?", (product_id,))
        product["component"] = [comp for (comp,) in cursor.fetchall()]

        # === Récupérer les tags ===
        cursor.execute("SELECT tag FROM product_tags WHERE product_id = ?", (product_id,))
        product["tags"] = [tag for (tag,) in cursor.fetchall()]

        return product
    

def delete_product(product_id: int) -> bool:

    """
    Supprime un produit et toutes ses occurrences dans les tables liées.
    Retourne True si la suppression a réussi.
    """

    tables_to_clean = [
        "reviews",
        "panier",
        "orders",
        "product_components",
        "product_tags",
        "pharmacy_products",
        "user_product_interactions",
    ]

    try:
        with get_connection() as conn:
            cur = conn.cursor()

            # Supprimer les références dans toutes les tables listées
            for table in tables_to_clean:
                cur.execute(f"DELETE FROM {table} WHERE product_id = ?", (product_id,))

            # Supprimer le produit lui-même
            cur.execute("DELETE FROM products WHERE id = ?", (product_id,))
            
            conn.commit()
        return True
    except Exception as e:
        print("Erreur suppression produit:", e)
        return False
    

def search_filter_product(query: str = "", 
                          selected_tags: list[str] | None = None,
                          selected_filters: dict | None = None,
                          min_score: int = 80  # score minimal pour accepter une correspondance
                          ) -> list[dict]:

    """
    Recherche et filtre les produits selon :
      - un mot-clé (dans le nom ou les tags)
      - un ensemble de tags sélectionnés (tous doivent être présents)
      - un dictionnaire de filtres { "categories", "ages", "providers", "prices" }

    Retourne une liste de produits (dicts) correspondant.
    """

    query = query.lower().strip() if query else ""  # La recherche ignore la case et les espaces
    selected_tags = selected_tags or []
    selected_filters = selected_filters or {
        "categories": set(),
        "ages": set(),
        "providers": set(),
        "prices": set(),
    }

    results = []

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM products")
        for (pid,) in cursor.fetchall():
            product = get_product(pid)
            if not product:
                continue

            # # === Recherche par texte ===
            # matches_search = (
            #     (query in product["name"].lower()) or
            #     any(query in t.lower() for t in product.get("tags", []))
            # ) if query else True

            # === Recherche par texte (fuzzy) ===
            matches_search = True
            if query:
                # Comparaison du nom
                name_score = fuzz.partial_ratio(query, product["name"].lower())
                
                # Comparaison des tags
                tags_score = max([fuzz.partial_ratio(query, t.lower()) for t in product.get("tags", [])], default=0)
                
                # On accepte si le score minimal est atteint
                matches_search = max(name_score, tags_score) >= min_score

            if not matches_search:
                continue

            # === Tags sélectionnés ===
            matches_tags = (
                all(t in product.get("tags", []) for t in selected_tags)
                if selected_tags else True
            )

            if not matches_tags:
                continue

            # === Catégories ===
            matches_category = (
                product["category"] in selected_filters["categories"]
                if selected_filters["categories"] else True
            )

            if not matches_category:
                continue

            # === Tranches d’âge ===
            matches_age = (
                product["age_group"] in selected_filters["ages"]
                if selected_filters["ages"] else True
            )

            if not matches_age:
                continue

            # === Fournisseurs ===
            matches_provider = (
                product["provider"] in selected_filters["providers"]
                if selected_filters["providers"] else True
            )

            if not matches_provider:
                continue

            # === Prix ===
            matches_price = True
            if selected_filters["prices"]:
                min_price_found = None
                price_info = get_min_price_for_product(product["id"])
                if price_info:
                    min_price_found = price_info["price"]

                # Si on a trouvé un prix, vérifier qu’il est dans au moins une des tranches sélectionnées
                if min_price_found is not None:
                    matches_price = any(
                        (mn <= min_price_found < mx)
                        for (mn, mx) in selected_filters["prices"]
                    )
                else:
                    matches_price = False  # produit non disponible

            if not matches_price:
                continue

            # === Vérification finale ===
            if all([matches_search, matches_tags, matches_category,
                    matches_age, matches_provider, matches_price]):
                results.append(product)

    return results


def get_filter_options(column):

    """Récupérer les options de filtre disponibles pour une colonne donnée (category, age_group, provider)."""

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT {column}, COUNT(*) FROM products GROUP BY {column}")

        return cursor.fetchall()  # Liste de tuples (valeur, count)
    

def count_products_in_price_range(min_price, max_price):

    """Compte le nombre de produits dont le prix minimum est dans une certaine fourchette."""
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM products")
        product_ids = [row[0] for row in cursor.fetchall()]
        count = 0
        for pid in product_ids:
            price_info = get_min_price_for_product(pid)
            if price_info and min_price <= price_info['price'] < max_price:
                count += 1

        return count
    

def get_pharmacy(pharmacy_id: int) -> dict | None:

    """Récupérer toutes les informations d'une pharmacie donnée (id, infos, produits)."""

    with get_connection() as conn:
        cursor = conn.cursor()

        # === Infos principales de la pharmacie ===
        cursor.execute("""
            SELECT id, name, address, latitude, longitude, phone_number
            FROM pharmacies
            WHERE id = ?
        """, (pharmacy_id,))
        row = cursor.fetchone()

        if not row:
            return None  # pharmacie inexistante

        pharmacy = {
            "id": row[0],
            "name": row[1],
            "address": row[2],
            "coords": {"lat": row[3], "lng": row[4]},
            "phone_number": row[5],
            "available_products": {}
        }

        # === Produits disponibles ===
        cursor.execute("""
            SELECT pp.product_id, pp.price, pp.qty
            FROM pharmacy_products pp
            WHERE pp.pharmacy_id = ?
        """, (pharmacy_id,))
        for product_id, price, qty in cursor.fetchall():
            pharmacy["available_products"][str(product_id)] = {
                "price": price,
                "qty": qty
            }

        return pharmacy
    

def delete_pharmacy(pharmacy_id: int) -> bool:

    """
    Supprime une pharmacie et toutes ses références dans les tables liées.
    Retourne True si la suppression a réussi.
    """

    try:
        with get_connection() as conn:
            cur = conn.cursor()

            # Supprimer les produits associés à la pharmacie
            cur.execute("DELETE FROM pharmacy_products WHERE pharmacy_id = ?", (pharmacy_id,))

            # Supprimer la pharmacie elle-même
            cur.execute("DELETE FROM pharmacies WHERE id = ?", (pharmacy_id,))

            conn.commit()
        return True

    except Exception as e:
        print("Erreur suppression pharmacie:", e)
        return False


def get_pharmacies_with_product(product_id: int) -> list[dict]:

    """Récupérer la liste des pharmacies qui possèdent un produit (quantité > 0) donné."""


    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT p.id, p.name, p.address, p.latitude, p.longitude, p.phone_number,
                   pp.price, pp.qty
            FROM pharmacies p
            JOIN pharmacy_products pp ON p.id = pp.pharmacy_id
            WHERE pp.product_id = ? AND pp.qty > 0
        """, (product_id,))

        pharmacies = []
        for row in cursor.fetchall():
            pharmacies.append({
                "id": row[0],
                "name": row[1],
                "address": row[2],
                "latitude": row[3],
                "longitude": row[4],
                "phone_number": row[5],
                "price": row[6],
                "qty": row[7],
            })

        return pharmacies
    

def get_products_in_pharmacy(pharmacy_id: int) -> list[dict]:

    """Récupérer la liste des produits disponibles (quantité > 0) dans une pharmacie donnée."""

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT pr.id, pr.name, pr.provider, pr.image, pr.description, pr.reference, pr.ordonnance,
                   pp.price, pp.qty
            FROM products pr
            JOIN pharmacy_products pp ON pr.id = pp.product_id
            WHERE pp.pharmacy_id = ? AND pp.qty > 0
        """, (pharmacy_id,))

        products = []
        for row in cursor.fetchall():
            products.append({
                "id": row[0],
                "name": row[1],
                "provider": row[2],
                "image": row[3],
                "description": row[4],
                "reference": row[5],
                "ordonnance": bool(row[6]),
                "price": row[7],
                "qty": row[8],
            })

        return products
    

def get_min_price_for_product(product_id: int) -> dict | None:

    """
    Retourne le prix le plus bas d'un produit (quantité > 0) et la pharmacie correspondante.
    Ex: {"pharmacy_id": 2, "pharmacy_name": "Pharmacie Centrale", "price": 2.99}
    """

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT p.id, p.name, pp.price, pp.qty
            FROM pharmacies p
            JOIN pharmacy_products pp ON p.id = pp.pharmacy_id
            WHERE pp.product_id = ? AND pp.qty > 0
            ORDER BY pp.price ASC
            LIMIT 1
        """, (product_id,))

        row = cursor.fetchone()
        if not row:
            return None  # produit indisponible dans toutes les pharmacies

        return {
            "pharmacy_id": row[0],
            "pharmacy_name": row[1],
            "price": row[2]
        }


def get_total_qty(product_id: int) -> int:

    """Retourne la quantité totale disponible pour un produit dans toutes les pharmacies."""

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT SUM(qty) 
            FROM pharmacy_products
            WHERE product_id = ?
        """, (product_id,))
        row = cursor.fetchone()
        return row[0] or 0
    

def get_total_price_for_product(product_id: int, quantity: int) -> dict:

    """
    Calcule le prix total pour une quantité donnée de produit en prenant d'abord les pharmacies les moins chères.
    
    Retourne un dict :
    {
        "success": bool,
        "total_price": float,
        "details": [
            {"pharmacy_id": 1, "pharmacy_name": "Pharmacie Centrale", "unit_price": 2.99, "taken_qty": 10},
            {"pharmacy_id": 3, "pharmacy_name": "Pharmacie du Centre", "unit_price": 3.10, "taken_qty": 5}
        ],
        "missing_qty": 0   # >0 si demande impossible
    }
    """

    with get_connection() as conn:
        cursor = conn.cursor()

        # Récupérer toutes les pharmacies qui ont ce produit, triées par prix croissant
        cursor.execute("""
            SELECT p.id, p.name, pp.price, pp.qty
            FROM pharmacies p
            JOIN pharmacy_products pp ON p.id = pp.pharmacy_id
            WHERE pp.product_id = ? AND pp.qty > 0
            ORDER BY pp.price ASC
        """, (product_id,))

        rows = cursor.fetchall()

        if not rows:
            return {"success": False, "total_price": 0.0, "details": [], "missing_qty": quantity}

        total_price = 0.0
        details = []
        remaining = quantity

        for pharmacy_id, pharmacy_name, price, stock in rows:
            if remaining <= 0:
                break

            take = min(stock, remaining)
            if take > 0:
                total_price += take * price
                details.append({
                    "pharmacy_id": pharmacy_id,
                    "pharmacy_name": pharmacy_name,
                    "unit_price": price,
                    "taken_qty": take
                })
                remaining -= take

        return {
            "success": remaining == 0,
            "total_price": total_price,
            "details": details,
            "missing_qty": remaining
        }


def remove_stock_product(product_id: int, qty: int) -> dict:

    """
    Retire une certaine quantité d'un produit (répartie sur les pharmacies les moins chères).
    Ne descend jamais sous 0.

    Retourne un dict avec le détail du retrait :
    {
        "success": bool,             # True si toute la quantité a pu être retirée
        "removed_qty": int,          # quantité effectivement retirée
        "missing_qty": int,          # quantité manquante si stock insuffisant
        "details": [                 # détail par pharmacie
            {"pharmacy_id": 1, "removed": 3},
            {"pharmacy_id": 2, "removed": 2}
        ]
    }
    """

    with get_connection() as conn:
        cursor = conn.cursor()

        remaining = qty
        details = []
        removed_total = 0

        # Récupérer les pharmacies classées par prix croissant
        cursor.execute("""
            SELECT pharmacy_id, price, qty
            FROM pharmacy_products
            WHERE product_id = ?
            ORDER BY price ASC
        """, (product_id,))

        pharmacies = cursor.fetchall()

        for pharmacy_id, price, stock_qty in pharmacies:
            if remaining <= 0:
                break

            if stock_qty <= 0:
                continue

            # Quantité à retirer dans cette pharmacie
            to_remove = min(stock_qty, remaining)

            # Mise à jour du stock
            cursor.execute("""
                UPDATE pharmacy_products
                SET qty = qty - ?
                WHERE product_id = ? AND pharmacy_id = ?
            """, (to_remove, product_id, pharmacy_id))

            details.append({"pharmacy_id": pharmacy_id, "removed": to_remove})
            removed_total += to_remove
            remaining -= to_remove

        conn.commit()

    return {
        "success": remaining == 0,
        "removed_qty": removed_total,
        "missing_qty": remaining,
        "details": details
    }


# === Gestion des tags ===
tag_colors = load_json("data/tags.json")


def get_tag_color(tag):

    return tag_colors.get(tag, "#9e9e9e")  # Gris si pas trouvé