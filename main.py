from telethon import TelegramClient, events
from dotenv import load_dotenv
import os
import re
import datetime
import smtplib
from email.mime.text import MIMEText

# =========================
# 🔐 LOAD ENV
# =========================

load_dotenv()

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
CHAT_ID = os.getenv("CHAT_ID")

# =========================
# 🤖 TELEGRAM CLIENT
# =========================

client = TelegramClient("session", api_id, api_hash)

# =========================
# 🔥 MODELOS IMPORTANTES
# =========================

HOT_MODELS = [
    "jordan", "jordan 4", "black cat", "military black",
    "dunk", "sb dunk", "air force",
    "yeezy", "new balance", "9060",
    "2002r", "samba", "asics"
]

# =========================
# 🧠 SCORE SYSTEM
# =========================

def calcular_score(texto, precios):

    score = 0
    texto = texto.lower()

    # modelos hot
    for model in HOT_MODELS:
        if model in texto:
            score += 20

    # link presente
    if "http" in texto:
        score += 10

    # precios
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
# 📧 EMAIL FUNCTION
# =========================

def enviar_email(subject, body):

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = EMAIL_USER

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()

    except Exception as e:
        print("Error email:", e)

# =========================
# 📊 HANDLER
# =========================

@client.on(events.NewMessage)
async def handler(event):

    text = event.raw_text
    lower = text.lower()

    links = re.findall(r'https?://\S+', text)
    prices = re.findall(r'\d+\€|\d+\$', text)

    if not links:
        return

    score = calcular_score(lower, prices)

    # SOLO DEALS BUENAS
    if score >= 40:

        message = f"""
🔥 TOP DEAL DETECTADA

📦 Producto:
{text}

🔗 Links:
{chr(10).join(links)}

💰 Precios:
{prices}

📊 Score: {score}
🕒 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
"""

        print(message)

        # guardar historial
        with open("deals.txt", "a", encoding="utf-8") as f:
            f.write(message + "\n" + "-"*60 + "\n")

        # =========================
        # 📲 TELEGRAM
        # =========================

        try:
            await client.send_message(int(CHAT_ID), message)
        except Exception as e:
            print("Error telegram:", e)

        # =========================
        # 📧 EMAIL
        # =========================

        enviar_email(
            "🔥 Sneaker Deal Encontrado",
            message
        )

# =========================
# 🚀 START
# =========================

print("🤖 BOT PRO V2 INICIADO...")

client.start()
client.run_until_disconnected()