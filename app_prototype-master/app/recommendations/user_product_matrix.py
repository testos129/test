import sqlite3
import pandas as pd
from pathlib import Path
import re

from app.services.users import get_panier


DATA_DIR = Path(__file__).resolve().parents[1] / 'data'
DB_FILE = DATA_DIR / 'data.db'
NEED_RECREATE = False


def get_connection():
    return sqlite3.connect(DB_FILE)


def init_interactions_table():

    """Initialise la table des interactions user/product."""

    with get_connection() as conn:
        cur = conn.cursor()
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
        conn.commit()
    print("✅ Table user_product_interactions initialisée.")


# Attention : n'inclut que les visites et panier actuel pour l'instant
def populate_interactions_from_db():

    """
    Reconstruit entièrement la table user_product_interactions à partir des données actuelles :
    - Panier (poids = quantité * 2)
    - Historique navigation (poids = visites * 1)
    - Achats (si table 'orders' existe : poids = quantité * 3)
    """

    with get_connection() as conn:
        cur = conn.cursor()

        # ⚠️ On vide la table avant de recalculer
        cur.execute("DELETE FROM user_product_interactions")
        print("⚠️  Anciennes données supprimées")
        conn.commit()

        # 1. Panier ⚠️ que panier actuelle et non historique, DIFFERENT DU COMPORTEMENT EN RUN
        cur.execute("SELECT user_id, product_id, quantity FROM panier")
        for user_id, product_id, qty in cur.fetchall():
            update_interaction(user_id, product_id, qty * 2)

        # 2. Historique navigation
        cur.execute("SELECT user_id, page, visits FROM user_history")
        for user_id, page, visits in cur.fetchall():
            # On cherche un product_id dans les URL de type /product/123 ou /product/123/itinerary
            match = re.match(r"^/product/(\d+)", page)
            if match:
                product_id = int(match.group(1))
                update_interaction(user_id, product_id, visits * 1)

        # 3. Achats
        try:
            cur.execute("SELECT user_id, product_id, qty FROM orders WHERE product_id != 0")  # product_id 0 exclu car il s'agit des frais de livraison
            for user_id, product_id, qty in cur.fetchall():
                update_interaction(user_id, product_id, qty * 3)
        except sqlite3.OperationalError:
            print("⚠️  Pas de table 'orders', étape ignorée.")

    print("✅ Table user_product_interactions remplie avec les données actuelles.")


def update_interaction(user_id: int, product_id: int, qty: int = 1, increment: int = 1):

    """
    Met à jour le score d'interaction pour (user_id, product_id).
    Si le couple n'existe pas encore → il est créé.
    """

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO user_product_interactions (user_id, product_id, score)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, product_id) DO UPDATE
            SET score = score + excluded.score
        """, (user_id, product_id, qty * increment))
        conn.commit()


def update_with_page(user_id, page):

    """Met à la jour le score d'interaction pour la visite d'une page produit"""

    match = re.match(r"^/product/(\d+)", page)
    if match:
        product_id = int(match.group(1))
        update_interaction(user_id, product_id, 1)


def update_with_panier(user_id: int):

    """Update les interactions avec l'intégralité du panier de l'utilisateur au moment de la commande."""

    panier = get_panier(user_id)
    
    for product_id, qty in panier.items():
        update_interaction(user_id, product_id, qty, increment = 5)


def build_interaction_matrix(db_path: str) -> pd.DataFrame:

    """
    Reconstruit une matrice (users x produits) avec les scores d'interaction.
    Le score est calculé comme suit: 
        - visit = + 1
        - clique d'ajout au panier (n'inclut pas les quantités) = + 5
        - commande = qty * + 5
    Retourne un DataFrame Pandas.
    """

    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query("""
            SELECT user_id, product_id, score
            FROM user_product_interactions
        """, conn)

    if df.empty:
        return pd.DataFrame()

    # Pivot en matrice user × produit
    matrix = df.pivot_table(index="user_id", columns="product_id", values="score", fill_value=0)

    return matrix


def build_reviews_matrix(db_path: str) -> pd.DataFrame:

    """
    Construit une matrice (users × produits) avec les notes données dans `reviews`.
    - La valeur est la note (rating).
    - Si pas de review pour un couple user/product, la valeur est -1.
    
    Retourne un DataFrame Pandas.
    """

    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query("""
            SELECT user_id, product_id, rating
            FROM reviews
        """, conn)

    if df.empty:
        return pd.DataFrame()

    # Pivot en matrice user × produit
    matrix = df.pivot_table(
        index="user_id",
        columns="product_id",
        values="rating",
        aggfunc="mean",  # au cas où plusieurs reviews existent pour le même couple
        fill_value=-1    # -1 quand pas de review
    )

    return matrix


def get_products_info_df(db_path: str) -> pd.DataFrame:

    """
    Récupère les informations produits avec colonnes :
    - product_id, description, provider
    - colonnes binaires pour chaque tag (tag_<nom>)
    - colonnes binaires pour chaque composant (comp_<nom>)
    - product_n_reviews : nombre de reviews pour chaque produit
    - product_avg_rating : note moyenne du produit
    Retourne un DataFrame Pandas.
    """

    with sqlite3.connect(db_path) as conn:
        # 1. Infos principales des produits
        df_products = pd.read_sql_query("""
            SELECT id AS product_id, name, description, provider
            FROM products
        """, conn)

        # 2. Tags
        df_tags = pd.read_sql_query("""
            SELECT product_id, tag
            FROM product_tags
        """, conn)

        if not df_tags.empty:
            df_tags_bin = (
                pd.get_dummies(df_tags["tag"], prefix="tag")
                .join(df_tags["product_id"])
                .groupby("product_id", as_index=False)
                .max()
            )
            df_products = df_products.merge(df_tags_bin, on="product_id", how="left")

        # 3. Composants
        df_comps = pd.read_sql_query("""
            SELECT product_id, component
            FROM product_components
        """, conn)

        if not df_comps.empty:
            df_comps_bin = (
                pd.get_dummies(df_comps["component"], prefix="comp")
                .join(df_comps["product_id"])
                .groupby("product_id", as_index=False)
                .max()
            )
            df_products = df_products.merge(df_comps_bin, on="product_id", how="left")
        
        # 4. Statistiques des reviews
        df_reviews = pd.read_sql_query("""
            SELECT product_id,
                   COUNT(*) AS product_n_reviews,
                   AVG(rating) AS product_avg_rating
            FROM reviews
            GROUP BY product_id
        """, conn)

        if not df_reviews.empty:
            df_products = df_products.merge(df_reviews, on="product_id", how="left")

    # 5. Remplir les NaN (produits sans tags ou composants)
    df_products = df_products.fillna(0)

    return df_products


def get_users_info_df(db_path: str) -> pd.DataFrame:

    """
    Récupère les informations utilisateurs avec colonnes :
    - user_id, username, email
    - user_n_reviews : nombre de reviews laissées
    - user_avg_rating : note moyenne donnée
    Retourne un DataFrame Pandas.
    """

    with sqlite3.connect(db_path) as conn:
        # 1. Infos principales des users
        df_users = pd.read_sql_query("""
            SELECT id AS user_id, username, email
            FROM users
        """, conn)

        # 2. Statistiques reviews par user
        df_reviews = pd.read_sql_query("""
            SELECT user_id,
                   COUNT(*) AS user_n_reviews,
                   AVG(rating) AS user_avg_rating
            FROM reviews
            GROUP BY user_id
        """, conn)

        if not df_reviews.empty:
            df_users = df_users.merge(df_reviews, on="user_id", how="left")

        # 3. Montant total dépensé par user
        df_amount = pd.read_sql_query("""
            SELECT  user_id,
                SUM(ABS(amount)) AS total_depenses
            FROM wallet_history
            WHERE description = 'Dépense'
            GROUP BY user_id;
        """, conn)

        if not df_amount.empty:
            df_users = df_users.merge(df_amount, on="user_id", how="left")

    # 4. Remplir les NaN (users sans reviews)
    df_users = df_users.fillna(0)

    return df_users


if __name__ == "__main__":

    # Initialiser la table
    if NEED_RECREATE:
        init_interactions_table()
        populate_interactions_from_db()

# run with python -m recommendations.user_product_matrix