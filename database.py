import sqlite3

conn = sqlite3.connect("data/deals.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product TEXT,
    link TEXT,
    price TEXT,
    score INTEGER,
    date TEXT
)
""")

conn.commit()

def save_deal(product, link, price, score, date):

    cursor.execute("""
    INSERT INTO deals (
        product,
        link,
        price,
        score,
        date
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        product,
        link,
        price,
        score,
        date
    ))

    conn.commit()