import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "data/deals.db"

def inject_test_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Modelos y grupos para variar
    models = ["Jordan 4 Black Cat", "Nike SB Dunk Low", "Yeezy Slide Bone", "Jordan 1 Retro High", "New Balance 9060"]
    groups = ["Sneaker Alerts EU", "Resale Kings", "Vinted Snipes", "Secret Cookgroup"]
    
    print("Inyectando deals de prueba en la base de datos...")
    
    # Generar 20 deals falsos repartidos en los últimos 7 días
    for _ in range(20):
        product = random.choice(models) + " Deadstock, chollo!"
        price = f"{random.randint(20, 80)}€"
        score = random.randint(60, 150)
        group = random.choice(groups)
        
        # Fecha aleatoria en los últimos 7 días
        days_ago = random.randint(0, 7)
        date = datetime.utcnow() - timedelta(days=days_ago)
        date_str = date.strftime('%Y-%m-%d %H:%M:%S UTC')
        
        link = f"https://vinted.com/item/{random.randint(100000, 999999)}"
        
        cursor.execute('''
            INSERT INTO deals (product, link, price, score, group_name, date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (product, link, price, score, group, date_str))
        
    conn.commit()
    conn.close()
    print("20 Deals de prueba inyectados correctamente!")

if __name__ == "__main__":
    inject_test_data()
