"""
Script para escanear el historial de Telegram y poblar la base de datos con deals reales.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

from database import DealDatabase
from scoring import calculate_score, extract_links, extract_prices

# =========================
# CONFIGURACIÓN
# =========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("TELETHON_SESSION", "data/session2")
SESSION_STRING = os.getenv("TELETHON_SESSION_STRING", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/deals.db")
ALERT_MIN_SCORE = int(os.getenv("ALERT_MIN_SCORE", "60"))
MESSAGES_LIMIT = 500  # Cuantos mensajes por grupo queremos leer del pasado

if not API_ID or not API_HASH:
    logger.error("API_ID y API_HASH son obligatorios en .env")
    raise RuntimeError("Falta API_ID o API_HASH")

db = DealDatabase(db_path=DATABASE_PATH)

if SESSION_STRING:
    client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)
else:
    client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)

async def scrape_historical_data():
    logger.info("Iniciando escaneo histórico de mensajes...")
    await client.start()
    
    two_weeks_ago = datetime.now(timezone.utc) - timedelta(days=14)
    
    # Recorrer todos los grupos y canales donde esté el usuario
    async for dialog in client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            logger.info(f"Escaneando grupo: {dialog.title}")
            
            messages_processed = 0
            deals_found = 0
            
            try:
                # Leer los últimos MESSAGES_LIMIT mensajes del grupo
                async for message in client.iter_messages(dialog.id, limit=MESSAGES_LIMIT):
                    if message.date and message.date < two_weeks_ago:
                        logger.info("Alcanzado el límite de 14 días. Pasando al siguiente grupo.")
                        break
                        
                    messages_processed += 1
                    text = message.message or ""
                    
                    if len(text) < 20:
                        continue
                        
                    links = extract_links(text)
                    if not links:
                        continue
                        
                    link = links[0]
                    # Si ya lo tenemos, saltar
                    if db.has_link(link):
                        continue
                        
                    prices = extract_prices(text)
                    score = calculate_score(text, prices)
                    
                    # Solo guardamos si supera el score
                    if score >= ALERT_MIN_SCORE:
                        product_text = " ".join(text.split())[:500]
                        price_text = ", ".join(prices) if prices else "No detectado"
                        
                        message_date = (
                            message.date.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
                            if message.date
                            else datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
                        )
                        
                        # Descarga opcional de imágenes
                        image_path = None
                        if message.media:
                            try:
                                os.makedirs("data/images", exist_ok=True)
                                downloaded = await message.download_media(file="data/images/")
                                if downloaded:
                                    image_path = os.path.relpath(downloaded, os.getcwd()).replace("\\", "/")
                                    logger.info(f"Foto histórica descargada: {image_path}")
                            except Exception as img_err:
                                logger.error(f"Error descargando foto histórica: {img_err}")
                        
                        saved = db.save_deal(
                            product=product_text,
                            link=link,
                            price=price_text,
                            score=score,
                            group_name=dialog.title,
                            date=message_date,
                            message_id=message.id,
                            user_id=message.sender_id,
                            image_path=image_path,
                        )
                        
                        if saved:
                            deals_found += 1
                            logger.info(f"✅ Deal encontrado! Score: {score} | Precio: {price_text}")
                            
            except Exception as e:
                logger.error(f"Error procesando el grupo {dialog.title}: {e}")
                
            logger.info(f"--> {dialog.title}: {messages_processed} procesados, {deals_found} deals reales extraídos.\n")
            
    logger.info("¡Escaneo completado!")
    
if __name__ == "__main__":
    asyncio.run(scrape_historical_data())
