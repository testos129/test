from services.users import get_visit_history
from services.items import get_connection, get_product


def find_similar_products(product_id: int, min_common_tags: int = 2) -> list[dict]:

    """
    Trouver les produits similaires à un produit donné en comparant les tags.
    Retourne une liste triée par nombre de tags en commun (décroissant).
    """

    current = get_product(product_id)
    if not current:
        return []

    current_tags = set(current.get("tags", []))

    similar = []
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM products WHERE id != ?", (product_id,))
        for (pid,) in cursor.fetchall():
            product = get_product(pid)
            if not product:
                continue
            common = current_tags & set(product.get("tags", []))
            if len(common) >= min_common_tags:
                product["common_tags"] = list(common)
                product["score"] = len(common)
                similar.append(product)

    # trier par nb de tags en commun
    return sorted(similar, key=lambda p: p["score"], reverse=True)


def recommend_products(user_id: int, min_common_tags: int = 2) -> list[dict]:

    """
    Recommande des produits en fonction de l'historique utilisateur et des tags.
    - Pondère les tags par le nombre de visites.
    - Exclut les produits déjà visités.
    """

    history = get_visit_history(user_id)  # {"/product/1": 3, "/product/2": 1, ...}
    if not history:
        return []

    visited_ids = set()
    tag_visits = {}

    # === Étape 1 : analyser l'historique ===
    for page, info in history.items():
        visits = info[1]
        if "/product/" in page:
            try:
                product_id = int(page.split("/")[-1])
            except ValueError:
                continue
            visited_ids.add(product_id)
            product = get_product(product_id)
            if product:
                for tag in product.get("tags", []):
                    tag_visits[tag] = tag_visits.get(tag, 0) + visits

    # === Étape 2 : trouver les top tags ===
    top_tags = dict(sorted(tag_visits.items(), key=lambda x: x[1], reverse=True)[:5])
    if not top_tags:
        return []

    # === Étape 3 : scorer les produits ===
    def product_score(prod: dict) -> int:

        score = 0
        for tag in prod.get("tags", []):
            if tag in top_tags:
                score += top_tags[tag]
        return score

    recommended = []
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM products")
        for (pid,) in cursor.fetchall():
            if pid in visited_ids:
                continue
            product = get_product(pid)
            if not product:
                continue
            score = product_score(product)
            if score > 0 and len(set(product.get("tags", [])) & set(top_tags)) >= min_common_tags:
                product["score"] = score
                recommended.append(product)

    # === Étape 4 : trier et renvoyer le top 5 ===
    return sorted(recommended, key=lambda p: p["score"], reverse=True)[:5]

            
