import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def generate_html_email(deals):
    html = """
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
          <h2 style="color: #FF4B4B; text-align: center;">🔥 Top Gangas de las Últimas 48h 🔥</h2>
          <p style="text-align: center; color: #555;">Aquí tienes la mejor selección de zapatillas detectadas por tu bot.</p>
          <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
    """
    
    if not deals:
        html += "<p style='text-align: center; color: #888;'>No se han encontrado deals de alta puntuación en los últimos 2 días.</p>"
    else:
        for idx, deal in enumerate(deals, 1):
            product = deal['product']
            price = deal['price']
            score = deal['score']
            link = deal['link']
            group = deal['group_name']
            
            html += f"""
            <div style="background: #fdfdfd; border: 1px solid #eee; padding: 15px; margin-bottom: 15px; border-radius: 5px;">
              <h3 style="margin-top: 0; color: #333;">#{idx}. {product}</h3>
              <p style="margin: 5px 0;"><strong>💰 Precio:</strong> <span style="color: #27ae60; font-size: 1.1em;">{price}</span></p>
              <p style="margin: 5px 0;"><strong>🎯 Score:</strong> {score} puntos</p>
              <p style="margin: 5px 0;"><strong>👥 Grupo:</strong> {group}</p>
              <a href="{link}" style="display: inline-block; margin-top: 10px; background-color: #FF4B4B; color: white; text-decoration: none; padding: 10px 15px; border-radius: 5px; font-weight: bold;">Ver Oferta</a>
            </div>
            """
            
    html += """
        </div>
      </body>
    </html>
    """
    return html

def generate_telegram_text(deals):
    if not deals:
        return "🤷‍♂️ *No hay súper gangas nuevas en las últimas 48h.*"
        
    text = "🔥 *TOP GANGAS - ÚLTIMAS 48H* 🔥\n\n"
    for idx, deal in enumerate(deals, 1):
        text += f"*{idx}. {deal['product']}*\n"
        text += f"💰 {deal['price']} | 🎯 Score: {deal['score']}\n"
        text += f"🔗 [Comprar aquí]({deal['link']})\n\n"
        
    return text

def send_summary_email(email_user, email_pass, html_content):
    if not email_user:
        logger.error("Destinatario de email (EMAIL_USER) no configurado.")
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
            data = {
                "from": "Sneaker Bot <onboarding@resend.dev>",
                "to": [email_user],
                "subject": "👟 Tu Resumen Diario de Sneakers",
                "html": html_content
            }
            req = urllib.request.Request(
                url, 
                data=json.dumps(data).encode("utf-8"), 
                headers=headers, 
                method="POST"
            )
            with urllib.request.urlopen(req) as response:
                logger.info("Email de resumen enviado con éxito via Resend")
            return
        except Exception as e:
            logger.error(f"Error enviando email de resumen via Resend: {e}")
            logger.info("Intentando fallback SMTP para resumen...")

    if not email_pass:
        logger.error("Credenciales SMTP no completas para el resumen.")
        return
        
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "👟 Tu Resumen Diario de Sneakers"
        msg["From"] = email_user
        msg["To"] = email_user
        
        part = MIMEText(html_content, "html", "utf-8")
        msg.attach(part)
        
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.starttls()
            server.login(email_user, email_pass)
            server.send_message(msg)
            
        logger.info("Email de resumen enviado con éxito via SMTP")
    except Exception as e:
        logger.error(f"Error enviando email de resumen via SMTP: {e}")

async def execute_summary(client, db, chat_id, email_user, email_pass):
    logger.info("Iniciando generación de resumen bisemanal...")
    
    # Obtener deals de los últimos 2 días con score alto (ej > 70)
    now = datetime.utcnow()
    two_days_ago = now - timedelta(days=2)
    start_date = two_days_ago.strftime('%Y-%m-%d %H:%M:%S')
    end_date = now.strftime('%Y-%m-%d %H:%M:%S')
    
    raw_deals = db.get_deals_by_date_range(start_date, end_date, min_score=70)
    
    # Filtrar solo el top 10
    top_deals = []
    for d in raw_deals:
        top_deals.append({
            'product': d['product'],
            'link': d['link'],
            'price': d['price'],
            'score': d['score'],
            'group_name': d['group_name']
        })
        
    # Ordenar por score y coger los 10 mejores
    top_deals = sorted(top_deals, key=lambda x: x['score'], reverse=True)[:10]
    
    # Enviar email
    html_email = generate_html_email(top_deals)
    send_summary_email(email_user, email_pass, html_email)
    
    # Enviar Telegram
    tg_text = generate_telegram_text(top_deals)
    if chat_id:
        try:
            await client.send_message(int(chat_id), tg_text, parse_mode='md')
            logger.info("Mensaje de resumen de Telegram enviado")
        except Exception as e:
            logger.error(f"Error enviando resumen por Telegram: {e}")
