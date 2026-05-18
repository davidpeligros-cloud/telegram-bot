"""
Bot de alertas de sneakers mejorado
Telethon + SQLite + Logging estructurado
"""

import asyncio
import logging
import os
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

from database import DealDatabase
from scoring import calculate_score, extract_links, extract_prices

# =========================
# LOGGING CONFIGURADO
# =========================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =========================
# LOAD ENV
# =========================

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
CHAT_ID = os.getenv("CHAT_ID") or os.getenv("ALERT_CHAT_ID")
ALERT_MIN_SCORE = int(os.getenv("ALERT_MIN_SCORE", "60"))
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/deals.db")
SESSION_NAME = os.getenv("TELETHON_SESSION", "data/session2")

if not API_ID or not API_HASH:
    logger.error("API_ID y API_HASH son obligatorios en .env")
    raise RuntimeError("Falta API_ID o API_HASH")

# =========================
# DATABASE
# =========================

db = DealDatabase(db_path=DATABASE_PATH)

# =========================
# TELEGRAM CLIENT
# =========================

client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)

# =========================
# ANTI DUPLICADOS
# =========================

sent_links = set()

# =========================
# UTILIDADES
# =========================

def send_email(subject: str, body: str) -> None:
    if not EMAIL_USER or not EMAIL_PASS:
        logger.debug("Email no enviado: credenciales no configuradas")
        return

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = EMAIL_USER

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)

        logger.info("Email enviado con éxito")
    except Exception as e:
        logger.error(f"Error enviando email: {e}")


def format_alert_message(link: str, score: int, price_text: str, product: str, group_name: str, message_date: str) -> str:
    return (
        f"🔥 TOP SNEAKER DEAL\n"
        f"\n"
        f"📊 Score: {score}\n"
        f"💰 Precio: {price_text}\n"
        f"🔗 Link: {link}\n"
        f"👟 Producto: {product}\n"
        f"👥 Grupo: {group_name}\n"
        f"🕒 Fecha: {message_date}\n"
    )


async def send_telegram_alert(chat_id: str, message: str) -> None:
    if not chat_id:
        logger.debug("CHAT_ID no configurado, omitiendo alerta Telegram")
        return

    try:
        await client.send_message(int(chat_id), message)
        logger.info("Alerta Telegram enviada")
    except Exception as e:
        logger.error(f"Error enviando Telegram: {e}")


async def periodic_cleanup(days: int = 90, interval_hours: int = 24) -> None:
    while True:
        try:
            deleted = db.delete_old_deals(days)
            if deleted > 0:
                logger.info(f"Limpieza periódica: eliminados {deleted} deals con más de {days} días")
        except Exception as e:
            logger.error(f"Error en limpieza periódica: {e}")

        await asyncio.sleep(interval_hours * 3600)

async def run_summary_loop():
    from send_summary import execute_summary
    
    while True:
        now = datetime.now()
        target = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        # Si ya ha pasado las 15:30 de hoy, programarlo para dentro de 2 días
        if now >= target:
            target += timedelta(days=2)
            
        sleep_seconds = (target - now).total_seconds()
        logger.info(f"Resumen bisemanal programado para: {target} (en {sleep_seconds/3600:.1f} horas)")
        
        await asyncio.sleep(sleep_seconds)
        
        try:
            await execute_summary(client, db, CHAT_ID, EMAIL_USER, EMAIL_PASS)
        except Exception as e:
            logger.error(f"Error ejecutando resumen: {e}")
            
        # Esperar 60 segundos extra para evitar dobles ejecuciones
        await asyncio.sleep(60)


@client.on(events.NewMessage)
async def handler(event) -> None:
    try:
        text = event.raw_text or ""
        if len(text) < 20:
            return

        links = extract_links(text)
        if not links:
            return

        link = links[0]
        if link in sent_links or db.has_link(link):
            logger.debug(f"Link duplicado ignorado: {link}")
            return

        prices = extract_prices(text)
        score = calculate_score(text, prices)
        if score < ALERT_MIN_SCORE:
            logger.debug(f"Score bajo ({score}), link descartado: {link}")
            return

        product_text = " ".join(text.split())[:500]
        price_text = ", ".join(prices) if prices else "No detectado"
        group_name = "Unknown Group"

        if getattr(event, "chat", None) is not None and getattr(event.chat, "title", None):
            group_name = event.chat.title
        elif getattr(event, "chat_id", None) is not None:
            group_name = str(event.chat_id)

        message_date = (
            event.message.date.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            if getattr(event, "message", None) and getattr(event.message, "date", None)
            else datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        )

        saved = db.save_deal(
            product=product_text,
            link=link,
            price=price_text,
            score=score,
            group_name=group_name,
            date=message_date,
            message_id=getattr(event.message, 'id', None),
            user_id=getattr(event.message, 'sender_id', None),
        )

        if not saved:
            logger.debug(f"Deal no guardado (posible duplicado): {link}")
            return

        sent_links.add(link)
        logger.info(f"Deal guardado: {link} | Score: {score}")

        alert_message = format_alert_message(
            link=link,
            score=score,
            price_text=price_text,
            product=product_text,
            group_name=group_name,
            message_date=message_date,
        )

        await send_telegram_alert(CHAT_ID, alert_message)
        send_email("🔥 Sneaker Deal Encontrado", alert_message)

    except Exception as e:
        logger.error(f"Error en handler: {e}", exc_info=True)


async def run_bot() -> None:
    while True:
        try:
            await client.start()
            logger.info("✅ Conectado a Telegram")
            asyncio.create_task(periodic_cleanup())
            asyncio.create_task(run_summary_loop())
            await client.run_until_disconnected()
        except SessionPasswordNeededError:
            logger.error("La sesión requiere contraseña de dos factores. Verifica tu cuenta de Telegram.")
            break
        except KeyboardInterrupt:
            logger.info("Bot detenido manualmente")
            break
        except Exception as e:
            logger.error(f"Error de conexión: {e}")
            logger.info("Reintentando en 30 segundos...")
            await asyncio.sleep(30)


def initialize_sent_links() -> None:
    try:
        sent_links.update(db.get_existing_links())
        logger.info(f"Cargados {len(sent_links)} links existentes desde la base de datos")
    except Exception as e:
        logger.error(f"Error inicializando anti-duplicados: {e}")


if __name__ == "__main__":
    logger.info("🤖 BOT SNEAKER INICIADO (v3.0)")
    initialize_sent_links()
    asyncio.run(run_bot())
