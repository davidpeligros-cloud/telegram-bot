from telethon import TelegramClient, events
from dotenv import load_dotenv
from database import save_deal

import os
import re
import datetime
import smtplib

from email.mime.text import MIMEText

# =========================
# LOAD ENV
# =========================

load_dotenv()

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

CHAT_ID = os.getenv("CHAT_ID")

# =========================
# TELEGRAM CLIENT
# =========================

client = TelegramClient(
    "session",
    api_id,
    api_hash
)

# =========================
# ANTI DUPLICADOS
# =========================

sent_links = set()

# =========================
# MODELOS HOT
# =========================

HOT_MODELS = [
    "jordan",
    "jordan 4",
    "black cat",
    "military black",
    "dunk",
    "sb dunk",
    "air force",
    "yeezy",
    "9060",
    "2002r",
    "samba",
    "asics"
]

# =========================
# SCORE
# =========================

def calcular_score(texto, precios):

    score = 0
    texto = texto.lower()

    for model in HOT_MODELS:

        if model in texto:
            score += 20

    if "http" in texto:
        score += 10

    for p in precios:

        nums = re.findall(r"\d+", p)

        if nums:

            price = int(nums[0])

            if price <= 30:
                score += 30

            elif price <= 50:
                score += 20

            elif price <= 80:
                score += 10

    return score

# =========================
# EMAIL
# =========================

def enviar_email(subject, body):

    try:

        msg = MIMEText(
            body,
            "plain",
            "utf-8"
        )

        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = EMAIL_USER

        server = smtplib.SMTP(
            "smtp.gmail.com",
            587
        )

        server.starttls()

        server.login(
            EMAIL_USER,
            EMAIL_PASS
        )

        server.send_message(msg)

        server.quit()

    except Exception as e:

        print("Error email:", e)

# =========================
# HANDLER
# =========================

@client.on(events.NewMessage)
async def handler(event):

    text = event.raw_text

    if len(text) < 20:
        return

    lower = text.lower()

    links = re.findall(
        r'https?://\S+',
        text
    )

    prices = re.findall(
        r'\d+(?:[.,]\d+)?\s?(?:€|\$)',
        text
    )

    if not links:
        return

    if links[0] in sent_links:
        return

    sent_links.add(links[0])

    score = calcular_score(
        lower,
        prices
    )

    if score < 60:
        return

    price_text = (
        ", ".join(prices)
        if prices else
        "No detectado"
    )

    clean_text = text[:500]

    message = f"""
🔥 TOP SNEAKER DEAL

📊 Score: {score}

💰 Precio:
{price_text}

🔗 Link:
{links[0]}

📝 Producto:
{clean_text}

🕒 Fecha:
{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
"""

    print(message)

    # =========================
    # GUARDAR DB
    # =========================

    save_deal(
        clean_text,
        links[0],
        price_text,
        score,
        datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M"
        )
    )

    # =========================
    # TELEGRAM
    # =========================

    try:

        await client.send_message(
            int(CHAT_ID),
            message
        )

    except Exception as e:

        print("Error telegram:", e)

    # =========================
    # EMAIL
    # =========================

    enviar_email(
        "Sneaker Deal Encontrado",
        message
    )

# =========================
# START
# =========================

print("BOT PRO V2 INICIADO...")

client.start()

client.run_until_disconnected()