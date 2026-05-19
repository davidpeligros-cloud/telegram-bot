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
import imaplib
import email
from email.header import decode_header
import re
import html

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
    if not EMAIL_USER:
        logger.debug("Email no enviado: destinatario (EMAIL_USER) no configurado")
        return

    resend_api_key = os.getenv("RESEND_API_KEY")
    if resend_api_key:
        try:
            import urllib.request
            import json
            url = "https://api.resend.com/emails"
            headers = {
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            html_body = f"<div style='font-family: sans-serif; white-space: pre-wrap;'>{body}</div>"
            data = {
                "from": "Sneaker Bot <onboarding@resend.dev>",
                "to": [EMAIL_USER],
                "subject": subject,
                "html": html_body
            }
            req = urllib.request.Request(
                url, 
                data=json.dumps(data).encode("utf-8"), 
                headers=headers, 
                method="POST"
            )
            with urllib.request.urlopen(req) as response:
                logger.info("Email enviado con éxito via Resend")
            return
        except Exception as e:
            logger.error(f"Error enviando email via Resend: {e}")
            logger.info("Intentando fallback SMTP...")

    if not EMAIL_PASS:
        logger.debug("Email no enviado: credenciales SMTP no configuradas")
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

        logger.info("Email enviado con éxito via SMTP")
    except Exception as e:
        logger.error(f"Error enviando email via SMTP: {e}")


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
        target = now.replace(hour=16, minute=0, second=0, microsecond=0)
        
        # Si ya ha pasado las 16:00 de hoy, programarlo para mañana
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
        
        status_color = "#e67e22" # Naranja para Pedido
        if status in ["Enviado", "En tránsito"]:
            status_color = "#3498db" # Azul
        elif status == "En reparto":
            status_color = "#f1c40f" # Amarillo
        elif status in ["Recibido", "En Stock"]:
            status_color = "#2ecc71" # Verde
        elif status == "Vendido":
            status_color = "#9b59b6" # Morado
            
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
    logger.info("Bucle de resumen de envíos iniciado (envíos activos diarios a las 16:00)")
    from zoneinfo import ZoneInfo
    madrid_tz = ZoneInfo("Europe/Madrid")
    while True:
        now = datetime.now(madrid_tz)
        target = now.replace(hour=16, minute=0, second=0, microsecond=0)
        
        # Si ya ha pasado las 16:00 de hoy, programarlo para mañana
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


# ==========================================
# EMAIL PARSER & LISTENER DAEMON (HACOO)
# ==========================================

def clean_html_body(html_content: str) -> str:
    text = re.sub(r'(?i)<br\s*/?>', '\n', html_content)
    text = re.sub(r'(?i)</p>', '\n', text)
    text = re.sub(r'(?i)</td>', '\t', text)
    text = re.sub(r'(?i)</tr>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()

def decode_header_val(header_str) -> str:
    if not header_str:
        return ""
    try:
        parts = decode_header(header_str)
        decoded = ""
        for part, encoding in parts:
            if isinstance(part, bytes):
                decoded += part.decode(encoding or "utf-8", errors="ignore")
            else:
                decoded += str(part)
        return decoded
    except Exception:
        return str(header_str)

def fetch_emails_sync() -> list:
    """
    Conecta a Gmail via IMAP, busca correos de Hacoo/Saramart,
    y devuelve una lista de diccionarios con la información de los correos nuevos.
    """
    results = []
    if not EMAIL_USER or not EMAIL_PASS:
        return results
        
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        
        # Carpetas a comprobar
        folders = ["INBOX", "[Gmail]/Todos", "[Gmail]/Spam"]
        
        for folder in folders:
            try:
                status, _ = mail.select(f'"{folder}"', readonly=True)
                if status != "OK":
                    continue
                
                # Buscar correos de Hacoo o Saramart en el cuerpo o asunto
                status, messages = mail.search(None, '(OR TEXT "Hacoo" TEXT "Saramart")')
                if status != "OK":
                    continue
                
                mail_ids = messages[0].split()
                # Tomar los 15 más recientes de esta carpeta
                for mail_id in mail_ids[-15:]:
                    try:
                        status, data = mail.fetch(mail_id, "(RFC822)")
                        if status != "OK":
                            continue
                        
                        raw_email = data[0][1]
                        msg = email.message_from_bytes(raw_email)
                        
                        msg_id = msg.get("Message-ID")
                        if not msg_id:
                            msg_id = f"{msg.get('Date')}_{msg.get('Subject')}"
                            
                        subject = decode_header_val(msg["Subject"])
                        sender = decode_header_val(msg["From"])
                        date_val = msg["Date"]
                        
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                content_disposition = str(part.get("Content-Disposition"))
                                if content_type == "text/plain" and "attachment" not in content_disposition:
                                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                    break
                                elif content_type == "text/html" and "attachment" not in content_disposition:
                                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        else:
                            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                            
                        if "<html>" in body.lower() or "<div" in body.lower() or "<body" in body.lower():
                            body = clean_html_body(body)
                            
                        results.append({
                            "msg_id": msg_id,
                            "subject": subject,
                            "sender": sender,
                            "date": date_val,
                            "body": body
                        })
                    except Exception as e:
                        logger.error(f"Error procesando correo individual en {folder}: {e}")
            except Exception as e:
                logger.error(f"Error accediendo a carpeta {folder}: {e}")
        mail.logout()
    except Exception as e:
        logger.error(f"Error general en fetch_emails_sync: {e}")
    return results

async def check_and_parse_emails() -> int:
    """
    Comprueba los correos de compra/envío de Hacoo/Saramart.
    Devuelve la cantidad de correos nuevos procesados.
    """
    logger.info("Buscando correos de compras/envíos en Gmail...")
    emails = await asyncio.to_thread(fetch_emails_sync)
    processed_count = 0
    
    for em in emails:
        msg_id = em["msg_id"]
        
        # Comprobar si ya procesamos este correo
        if db.is_email_processed(msg_id):
            continue
            
        body = em["body"]
        subject = em["subject"]
        
        # --- PARSER DE HACOO / SARAMART ---
        order_match = re.search(r'(?:pedido|pedido\.|pedido:)\s*(\d{10,})', body, re.IGNORECASE)
        if not order_match:
            order_match = re.search(r'(?:Nº\s*de\s*pedido\.?|Nº\s*pedido\.?)\s*\n?\s*(\d{10,})', body, re.IGNORECASE)
            
        order_num = order_match.group(1) if order_match else None
        
        if order_num:
            is_confirmation = any(x in body.lower() or x in subject.lower() for x in ["confirmado", "pago del pedido", "gracias por elegir", "hemos recibido tu pago"])
            is_shipping = any(x in body.lower() or x in subject.lower() for x in ["enviado", "seguimiento", "tracking", "código de envío", "su paquete ha sido"])
            
            if is_confirmation:
                # Nombre de producto
                prod_match = re.search(r'(?:Resumen de la orden|Resumen del pedido|Resumen de la compra)\s*\n\s*(.*?)\s*\n', body, re.IGNORECASE)
                product_name = prod_match.group(1).strip() if prod_match else None
                
                if not product_name:
                    lines = body.split("\n")
                    for i, line in enumerate(lines):
                        if "talla:" in line.lower() and i > 0:
                            product_name = lines[i-1].strip()
                            break
                if not product_name:
                    product_name = f"Pedido Hacoo {order_num}"
                    
                size_match = re.search(r'(?:Talla|Size):\s*(\w+)', body, re.IGNORECASE)
                size = size_match.group(1).strip() if size_match else None
                
                style_match = re.search(r'(?:Estilo|Style):\s*(.*?)\s*\n', body, re.IGNORECASE)
                style = style_match.group(1).strip() if style_match else ""
                
                price_match = re.search(r'(?:Producto total|Total del producto|Precio del producto)\s*[\t ]*\s*([\d,.]+)\s*€', body, re.IGNORECASE)
                purchase_price = 0.0
                if price_match:
                    purchase_price = float(price_match.group(1).replace(",", "."))
                    
                fees_match = re.search(r'(?:Costo de envío|Gastos de envío|Envío)\s*[\t ]*\s*([\d,.]+)\s*€', body, re.IGNORECASE)
                fees = 0.0
                if fees_match:
                    fees = float(fees_match.group(1).replace(",", "."))
                    
                # Evitar guardar si ya existe el pedido registrado
                already_exists = False
                all_shipments = db.get_all_shipments()
                for s in all_shipments:
                    s_dict = dict(s)
                    if s_dict["tracking_number"] == order_num or (s_dict["notes"] and order_num in s_dict["notes"]):
                        already_exists = True
                        break
                        
                if not already_exists:
                    saved = db.save_shipment(
                        product_name=product_name,
                        carrier="Hacoo",
                        tracking_number=order_num,
                        status="Pedido",
                        notes=f"Nº de pedido: {order_num}. Estilo: {style}",
                        purchase_price=purchase_price,
                        resell_price=purchase_price * 1.5,
                        fees=fees,
                        size=size,
                        store="Hacoo"
                    )
                    if saved:
                        logger.info(f"Pedido Hacoo {order_num} importado desde email con éxito!")
                        alert_text = (
                            f"📦 **Nueva compra detectada en tu correo**\n\n"
                            f"👟 **{product_name}**\n"
                            f"📏 Talla: `{size or 'N/A'}`\n"
                            f"💰 Compra: `{purchase_price:.2f} €` (+ `{fees:.2f} €` envío)\n"
                            f"🏪 Tienda: `Hacoo`\n"
                            f"🔢 Pedido: `{order_num}`\n\n"
                            f"Registrado automáticamente en tu inventario."
                        )
                        try:
                            await client.send_message(int(CHAT_ID), alert_text)
                        except Exception as te:
                            logger.error(f"Error enviando alerta de Telegram: {te}")
                        processed_count += 1
                        
            elif is_shipping:
                tracking_match = re.search(r'(?:tracking|seguimiento|código|nº de envío|nº envío):\s*(\w+)', body, re.IGNORECASE)
                if not tracking_match:
                    tracking_match = re.search(r'\b([A-Z]{2}\d{9}[A-Z]{2}|\d{16,24}|[A-Z0-9]{12,24})\b', body)
                    
                new_tracking = tracking_match.group(1) if tracking_match else None
                
                carrier_name = "Correos"
                for c in ["Correos Express", "Correos", "SEUR", "DHL", "GLS", "UPS", "FedEx", "Mondial Relay", "InPost", "Nacex"]:
                    if c.lower() in body.lower():
                        carrier_name = c
                        break
                        
                if new_tracking and new_tracking != order_num:
                    matched_shipment = None
                    all_shipments = db.get_all_shipments()
                    for s in all_shipments:
                        s_dict = dict(s)
                        if s_dict["tracking_number"] == order_num or (s_dict["notes"] and order_num in s_dict["notes"]):
                            matched_shipment = s_dict
                            break
                            
                    if matched_shipment:
                        if matched_shipment["status"] not in ["En tránsito", "En reparto", "En Stock", "Vendido"]:
                            success = db.update_shipment_status(
                                shipment_id=matched_shipment["id"],
                                new_status="En tránsito",
                                tracking_number=new_tracking,
                                carrier=carrier_name
                            )
                            if success:
                                logger.info(f"Envío de pedido Hacoo {order_num} actualizado a En tránsito con tracking {new_tracking}.")
                                alert_text = (
                                    f"🚚 **¡Tu pedido ya ha sido enviado!**\n\n"
                                    f"👟 **{matched_shipment['product_name']}**\n"
                                    f"📦 Transportista: `{carrier_name}`\n"
                                    f"🔢 Tracking: `{new_tracking}`\n\n"
                                    f"Actualizado automáticamente en tu inventario."
                                )
                                try:
                                    await client.send_message(int(CHAT_ID), alert_text)
                                except Exception as te:
                                    logger.error(f"Error enviando alerta de Telegram: {te}")
                                processed_count += 1
                                
        db.mark_email_processed(msg_id)
        
    return processed_count

async def run_email_listener_loop() -> None:
    logger.info("Bucle de escucha de correos de compras/envíos iniciado (cada 10 minutos)")
    if not EMAIL_USER or not EMAIL_PASS:
        logger.warning("Falta EMAIL_USER o EMAIL_PASS en el entorno. Escucha de correos desactivada.")
        return
        
    # Esperar 30 segundos al inicio
    await asyncio.sleep(30)
    
    while True:
        try:
            await check_and_parse_emails()
        except Exception as e:
            logger.error(f"Error en run_email_listener_loop: {e}")
            
        await asyncio.sleep(600)



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
        logger.info(f"Comando recibido: '{event.raw_text}' de sender_id: {event.sender_id} (is_private: {event.is_private})")
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
                "• `/probar_correo` - Fuerza el envío del email diario ahora mismo.\n"
                "• `/probar_lector` - Fuerza la búsqueda de nuevos pedidos en tu Gmail ahora mismo.\n"
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
            
        elif command == "/probar_correo":
            await event.respond("⚡ Iniciando envío manual de resumen diario por correo...")
            from send_summary import execute_summary
            try:
                await execute_summary(client, db, CHAT_ID, EMAIL_USER, EMAIL_PASS)
                await event.respond("✅ Resumen diario ejecutado y enviado.")
            except Exception as e:
                await event.respond(f"❌ Error al enviar el correo: {e}")
                
        elif command == "/probar_lector":
            await event.respond("⚡ Buscando y procesando correos de compras/envíos en Gmail...")
            try:
                processed = await check_and_parse_emails()
                await event.respond(f"✅ Búsqueda finalizada. Se han procesado e importado {processed} nuevos correos de compras/envíos.")
            except Exception as e:
                await event.respond(f"❌ Error al procesar correos: {e}")
            
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
                if status in ["Enviado", "En tránsito"]:
                    status_emoji = "🚚"
                elif status == "En reparto":
                    status_emoji = "🛵"
                elif status in ["Recibido", "En Stock"]:
                    status_emoji = "👟"
                elif status == "Vendido":
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
            asyncio.create_task(run_email_listener_loop())
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
