"""
Script local para generar una StringSession para Railway.
"""
import os
from dotenv import load_dotenv
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

if not API_ID or not API_HASH:
    print("❌ ERROR: Faltan API_ID o API_HASH en el archivo .env")
    exit(1)

print("Iniciando conexión con Telegram para generar la sesión...")
with TelegramClient(StringSession(), int(API_ID), API_HASH) as client:
    session_string = client.session.save()
    print("\n" + "="*50)
    print("✅ SESIÓN GENERADA CON ÉXITO ✅")
    print("="*50)
    print("Copia exactamente el siguiente texto y ponlo en Railway como valor de la variable TELETHON_SESSION_STRING:\n")
    print(session_string)
    print("\n" + "="*50)
