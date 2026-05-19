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
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

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
SESSION_STRING = os.getenv("TELETHON_SESSION_STRING", "")

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

if SESSION_STRING:
    logger.info("Usando StringSession desde variables de entorno.")
    client = TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH)
else:
    logger.info("Usando sesión SQLite local.")
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
    from zoneinfo import ZoneInfo
    madrid_tz = ZoneInfo("Europe/Madrid")
    
    while True:
        now = datetime.now(madrid_tz)
        target = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        # Si ya ha pasado las 15:30 de hoy, programarlo para mañana
        if now >= target:
            target += timedelta(days=1)
            
        # Guardar la fecha en un archivo para que el dashboard lo lea
        try:
            with open("data/next_summary.txt", "w") as f:
                f.write(target.isoformat())
        except Exception as e:
            logger.error(f"Error guardando fecha de resumen: {e}")
            
        sleep_seconds = (target - now).total_seconds()
        logger.info(f"Resumen diario programado para: {target} (en {sleep_seconds/3600:.1f} horas)")
        
        await asyncio.sleep(sleep_seconds)
        
        try:
            await execute_summary(client, db, CHAT_ID, EMAIL_USER, EMAIL_PASS)
        except Exception as e:
            logger.error(f"Error ejecutando resumen: {e}")
            
        # Esperar 60 segundos extra para evitar dobles ejecuciones
        await asyncio.sleep(60)


def generate_shipments_email_html(shipments) -> str:
    html = """
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #f4f4f6; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
          <h2 style="color: #2e7d32; text-align: center; margin-bottom: 5px;">📦 Estado de tus Envíos Activos 📦</h2>
          <p style="text-align: center; color: #666; margin-top: 0; font-size: 0.95em;">Aquí tienes el resumen diario de tus compras en camino.</p>
          <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
    """
    for ship in shipments:
        name = ship['product_name']
        carrier = ship['carrier']
        tracking = ship['tracking_number']
        status = ship['status']
        notes = ship['notes'] or "Sin notas adicionales."
        
        # Generar enlaces oficiales de seguimiento automáticos
        tracking_url = "#"
        carrier_lower = carrier.lower()
        if "correosexpress" in carrier_lower or "correos express" in carrier_lower:
            tracking_url = f"https://www.correosexpress.com/web/correosexpress/consultanos?numEnvio={tracking}"
        elif "correos" in carrier_lower:
            tracking_url = f"https://www.correos.es/es/es/herramientas/localizador/detalle?cod_envio={tracking}"
        elif "seur" in carrier_lower:
            tracking_url = f"https://www.seur.com/livetracking/pages/seguimiento-online-busqueda.do?excode={tracking}"
        elif "dhl" in carrier_lower:
            tracking_url = f"https://www.dhl.com/es-es/home/tracking/tracking-express.html?submit=1&tracking-id={tracking}"
        
        status_color = "#e67e22" # Naranja para Pedido/Enviado
        if status == "En reparto":
            status_color = "#3498db" # Azul
        elif status == "Recibido":
            status_color = "#2ecc71" # Verde
            
        html += f"""
        <div style="background: #fafafa; border-left: 5px solid {status_color}; padding: 15px; margin-bottom: 15px; border-radius: 4px;">
          <h3 style="margin-top: 0; color: #333; margin-bottom: 10px;">{name}</h3>
          <p style="margin: 4px 0; font-size: 0.9em; color: #555;"><strong>🚚 Transportista:</strong> {carrier}</p>
          <p style="margin: 4px 0; font-size: 0.9em; color: #555;"><strong>🔢 Código Seguimiento:</strong> <span style="font-family: monospace; background: #eef2f3; padding: 2px 6px; border-radius: 3px; font-weight: bold; color: #2c3e50;">{tracking}</span></p>
          <p style="margin: 4px 0; font-size: 0.9em; color: #555;"><strong>📍 Estado Actual:</strong> <span style="color: {status_color}; font-weight: bold; background: {status_color}15; padding: 1px 6px; border-radius: 3px;">{status}</span></p>
          <p style="margin: 10px 0 0 0; color: #777; font-size: 0.85em; font-style: italic; border-top: 1px dashed #eee; padding-top: 8px;">📝 {notes}</p>
        """
        if tracking_url != "#":
            html += f'<a href="{tracking_url}" target="_blank" style="display: inline-block; margin-top: 12px; background-color: #2e7d32; color: white; text-decoration: none; padding: 8px 14px; border-radius: 6px; font-weight: bold; font-size: 0.85em; box-shadow: 0 2px 4px rgba(46,125,50,0.2);">Rastrear Paquete</a>'
        html += "</div>"
        
    html += """
          <p style="font-size: 0.8em; color: #999; text-align: center; margin-top: 30px;">
            Este correo es enviado automáticamente por tu Sneaker Bot. Puedes gestionar tus paquetes desde el Dashboard de Streamlit.
          </p>
        </div>
      </body>
    </html>
    """
    return html


async def run_shipments_report_loop():
    logger.info("Bucle de resumen de envíos iniciado (envíos activos diarios a las 15:30)")
    from zoneinfo import ZoneInfo
    madrid_tz = ZoneInfo("Europe/Madrid")
    while True:
        now = datetime.now(madrid_tz)
        target = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        # Si ya ha pasado las 15:30 de hoy, programarlo para mañana
        if now >= target:
            target += timedelta(days=1)
            
        sleep_seconds = (target - now).total_seconds()
        logger.info(f"Reporte diario de envíos programado para: {target} (en {sleep_seconds/3600:.1f} horas)")
        
        await asyncio.sleep(sleep_seconds)
        
        try:
            active_shipments = db.get_active_shipments()
            # Convertir rows de sqlite a diccionarios
            shipments_list = [dict(row) for row in active_shipments]
            
            if shipments_list and EMAIL_USER and EMAIL_PASS:
                logger.info("Generando reporte de envíos activos diarios...")
                html_content = generate_shipments_email_html(shipments_list)
                
                msg = MIMEMultipart("alternative")
                msg["Subject"] = "📦 Resumen Diario de tus Envíos Activos"
                msg["From"] = EMAIL_USER
                msg["To"] = EMAIL_USER
                
                part = MIMEText(html_content, "html", "utf-8")
                msg.attach(part)
                
                with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
                    server.starttls()
                    server.login(EMAIL_USER, EMAIL_PASS)
                    server.send_message(msg)
                    
                logger.info("Reporte diario de envíos enviado con éxito")
            else:
                logger.info("No hay envíos activos o faltan credenciales de email. Reporte omitido.")
        except Exception as e:
            logger.error(f"Error en bucle de reporte de envíos: {e}", exc_info=True)
            
        # Esperar 60 segundos extra para evitar dobles ejecuciones
        await asyncio.sleep(60)



@client.on(events.NewMessage)
async def handler(event) -> None:
    try:
        text = event.raw_text or ""
        if text.startswith("/") or len(text) < 20:
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

        # Descarga opcional de imágenes
        image_path = None
        if event.message.media:
            try:
                os.makedirs("data/images", exist_ok=True)
                downloaded = await event.message.download_media(file="data/images/")
                if downloaded:
                    image_path = os.path.relpath(downloaded, os.getcwd()).replace("\\", "/")
                    logger.info(f"Foto descargada con éxito: {image_path}")
            except Exception as img_err:
                logger.error(f"Error descargando foto del mensaje: {img_err}")

        saved = db.save_deal(
            product=product_text,
            link=link,
            price=price_text,
            score=score,
            group_name=group_name,
            date=message_date,
            message_id=getattr(event.message, 'id', None),
            user_id=getattr(event.message, 'sender_id', None),
            image_path=image_path,
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


@client.on(events.NewMessage(pattern=r'^/'))
async def command_handler(event) -> None:
    try:
        # Solo procesar comandos en chats privados
        if not event.is_private:
            return

        # Comprobar seguridad: solo responder si el remitente es el dueño o coincide con CHAT_ID
        me = await client.get_me()
        is_owner = event.sender_id == me.id
        
        is_authorized = is_owner
        if not is_owner and CHAT_ID:
            try:
                # Si el CHAT_ID coincide con el sender_id del mensaje privado
                if int(CHAT_ID) == event.sender_id:
                    is_authorized = True
            except Exception:
                pass
                
        if not is_authorized:
            logger.warning(f"Intento de comando no autorizado de user ID: {event.sender_id}")
            return

        text = event.raw_text.strip()
        parts = text.split(" ", 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command == "/help" or command == "/start":
            help_text = (
                "🤖 **Asistente Sneaker Bot**\n\n"
                "Usa estos comandos desde nuestro chat privado:\n"
                "• `/resumen` - Ver los 5 mejores chollos de las últimas 24h.\n"
                "• `/envios` - Ver un resumen de tus paquetes activos.\n"
                "• `/buscar <zapato>` - Buscar chollos en el historial.\n"
                "• `/help` - Muestra esta ayuda."
            )
            await event.respond(help_text)
            
        elif command == "/resumen":
            # Chollos últimas 24 horas (convertido a UTC)
            one_day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S UTC')
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT product, link, price, score, group_name FROM deals WHERE date >= ? ORDER BY score DESC LIMIT 5",
                    (one_day_ago,)
                )
                deals = cursor.fetchall()
                
            if not deals:
                await event.respond("📭 No se han registrado chollos en las últimas 24 horas.")
                return
                
            response = "🔥 **Top 5 Chollos (Últimas 24h)**:\n\n"
            for product, link, price, score, group_name in deals:
                response += f"• **{product[:50]}...**\n  💰 Precio: {price} | 🔥 Score: {score}\n  🛍️ [Ir a la oferta]({link})\n\n"
            await event.respond(response, link_preview=False)
            
        elif command == "/envios":
            active_shipments = db.get_active_shipments()
            shipments_list = [dict(s) for s in active_shipments]
            
            if not shipments_list:
                await event.respond("📦 No tienes ningún envío activo en tránsito en este momento.")
                return
                
            response = "📦 **Tus Envíos Activos**:\n\n"
            for s in shipments_list:
                name = s['product_name']
                carrier = s['carrier']
                tracking = s['tracking_number']
                status = s['status']
                
                status_emoji = "⏳"
                if status == "Enviado":
                    status_emoji = "🚚"
                elif status == "En reparto":
                    status_emoji = "🛵"
                elif status == "Recibido":
                    status_emoji = "✅"
                    
                response += f"• {status_emoji} **{name}**\n  🚚 {carrier} | 🔢 `{tracking}`\n  📍 Estado: **{status}**\n\n"
            await event.respond(response)
            
        elif command == "/buscar":
            if not args:
                await event.respond("⚠️ Por favor introduce un término. Ej: `/buscar jordan`")
                return
                
            deals = db.search_deals(args)
            if not deals:
                await event.respond(f"🔍 No se han encontrado chollos coincidentes con '{args}'.")
                return
                
            # Tomar top 5
            deals_sorted = sorted(deals, key=lambda x: x[4], reverse=True)[:5]
            response = f"🔍 **Resultados para '{args}' (Top 5)**:\n\n"
            for d in deals_sorted:
                product = d[1]
                link = d[2]
                price = d[3]
                score = d[4]
                response += f"• **{product[:50]}...**\n  💰 Precio: {price} | 🔥 Score: {score}\n  🛍️ [Ir a la oferta]({link})\n\n"
            await event.respond(response, link_preview=False)
            
    except Exception as e:
        logger.error(f"Error procesando comando: {e}", exc_info=True)


async def run_bot() -> None:
    while True:
        try:
            await client.start()
            logger.info("✅ Conectado a Telegram")
            asyncio.create_task(periodic_cleanup())
            asyncio.create_task(run_summary_loop())
            asyncio.create_task(run_shipments_report_loop())
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
