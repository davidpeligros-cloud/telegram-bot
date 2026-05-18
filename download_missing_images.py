import asyncio
import logging
import os
import sqlite3
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from database import DealDatabase

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

if not API_ID or not API_HASH:
    logger.error("API_ID y API_HASH son obligatorios en .env")
    raise RuntimeError("Falta API_ID o API_HASH")

if SESSION_STRING:
    client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)
else:
    client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)

async def download_missing_images():
    logger.info("Iniciando la recuperación de imágenes faltantes...")
    # Asegurar que las migraciones de base de datos se ejecutan
    DealDatabase(db_path=DATABASE_PATH)
    await client.start()
    
    logger.info("Obteniendo diálogos de Telegram para mapear canales...")
    dialogs = await client.get_dialogs()
    entity_map = {d.title: d.entity for d in dialogs}
    for d in dialogs:
        entity_map[str(d.id)] = d.entity
        entity_map[d.id] = d.entity
    
    # 1. Obtener deals sin imagen pero con message_id y group_name
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT id, product, group_name, message_id 
        FROM deals 
        WHERE (image_path IS NULL OR image_path = '') 
          AND message_id IS NOT NULL 
          AND group_name IS NOT NULL
        ORDER BY date DESC
        """
    )
    deals = cursor.fetchall()
    logger.info(f"Se han encontrado {len(deals)} ofertas sin imagen para procesar.")
    
    if not deals:
        logger.info("¡Todas las ofertas tienen imagen o no hay nada que recuperar!")
        conn.close()
        return
        
    os.makedirs("data/images", exist_ok=True)
    downloaded_count = 0
    
    for deal in deals:
        deal_id = deal['id']
        product = deal['product']
        group = deal['group_name']
        msg_id = deal['message_id']
        
        logger.info(f"Procesando Deal #{deal_id}: {product[:40]}... (Grupo: {group}, Msg ID: {msg_id})")
        
        entity = entity_map.get(group)
        if not entity:
            entity = entity_map.get(str(group))
            
        if not entity:
            logger.warning(f"No se pudo encontrar el canal/grupo '{group}' en tus diálogos de Telegram.")
            continue
            
        try:
            # Obtener el mensaje usando la entidad resuelta
            msg = await client.get_messages(entity, ids=msg_id)
            if msg and msg.media:
                logger.info(f"¡Media encontrado para Deal #{deal_id}! Descargando...")
                downloaded = await msg.download_media(file="data/images/")
                if downloaded:
                    # Guardar ruta relativa
                    rel_path = os.path.relpath(downloaded, os.getcwd()).replace("\\", "/")
                    
                    # Actualizar en base de datos
                    cursor.execute(
                        "UPDATE deals SET image_path = ? WHERE id = ?",
                        (rel_path, deal_id)
                    )
                    conn.commit()
                    downloaded_count += 1
                    logger.info(f"Imagen guardada en: {rel_path}")
                else:
                    logger.warning(f"No se pudo descargar el media para Deal #{deal_id}")
            else:
                logger.info(f"El mensaje #{msg_id} en {group} no contiene multimedia.")
                
        except Exception as e:
            logger.error(f"Error procesando Deal #{deal_id}: {e}")
            
        # Pequeño delay de cortesía para no saturar la API de Telegram
        await asyncio.sleep(1)
        
    conn.close()
    logger.info(f"Proceso finalizado. Se han recuperado {downloaded_count} imágenes exitosamente.")

if __name__ == "__main__":
    asyncio.run(download_missing_images())
