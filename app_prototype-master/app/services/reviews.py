import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / 'data'
DB_PATH = DATA_DIR / 'data.db'

def get_connection():
    return sqlite3.connect(DB_PATH)


def get_review_infos(review_id: int) -> dict | None:

    """Renvoie toutes les infos d'un avis sous forme de dictionnaire."""

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, product_id, user_id, rating, comment, date, modified, editing
            FROM reviews
            WHERE id = ?
        """, (review_id,))
        row = cursor.fetchone()
        
        if not row:
            return None

        review_id, product_id, user_id, rating, comment, date, modified, editing = row

        return {
            "id": review_id,
            "product_id": product_id,
            "user_id": user_id,
            "rating": rating,
            "comment": comment,
            "date": date,
            "modified": bool(modified),
            "editing": bool(editing),
        }


def get_average_rating(product_id: int):

    """Retourne la note moyenne pour un produit (ou None si pas d'avis)."""

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT AVG(rating) FROM reviews WHERE product_id = ?", (product_id,)
        )
        row = cursor.fetchone()

        return row[0] if row and row[0] is not None else None


def get_number_of_reviews(product_id: int):

    """Retourne le nombre d'avis pour un produit."""

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM reviews WHERE product_id = ?", (product_id,)
        )
        row = cursor.fetchone()

        return row[0] if row else 0
    

def get_reviews(product_id: int):

    """Retourne la liste complète des avis d'un produit (les plus récents en premier)."""

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, rating, comment, date, modified
            FROM reviews
            WHERE product_id = ?
            ORDER BY date DESC
            """,
            (product_id,),
        )
        rows = cursor.fetchall()

        reviews = []
        for row in rows:
            reviews.append({
                "user": row[0],
                "rating": row[1],
                "comment": row[2],
                "date": row[3],
                "modified": bool(row[4]),
            })

        return reviews