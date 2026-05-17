import sqlite3
import os

# =========================
# CREAR CARPETA DATA
# =========================

os.makedirs("data", exist_ok=True)

# =========================
# CONEXIÓN DB
# =========================

conn = sqlite3.connect(
    "data/deals.db",
    check_same_thread=False
)

cursor = conn.cursor()

# =========================
# TABLA
# =========================

cursor.execute("""
CREATE TABLE IF NOT EXISTS deals (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    product TEXT,
    link TEXT UNIQUE,
    price TEXT,
    score INTEGER,

    group_name TEXT,

    date TEXT
)
""")

conn.commit()

# =========================
# GUARDAR DEAL
# =========================

def save_deal(
    product,
    link,
    price,
    score,
    group_name,
    date
):

    try:

        cursor.execute("""
        INSERT INTO deals (

            product,
            link,
            price,
            score,
            group_name,
            date

        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (

            product,
            link,
            price,
            score,
            group_name,
            date

        ))

        conn.commit()

    except:
        pass

# =========================
# TOP GRUPOS
# =========================

def top_groups():

    cursor.execute("""
    SELECT
        group_name,
        COUNT(*)

    FROM deals

    GROUP BY group_name

    ORDER BY COUNT(*) DESC

    LIMIT 10
    """)

    return cursor.fetchall()

# =========================
# TOP DEALS
# =========================

def top_deals():

    cursor.execute("""
    SELECT
        product,
        score

    FROM deals

    ORDER BY score DESC

    LIMIT 10
    """)

    return cursor.fetchall()