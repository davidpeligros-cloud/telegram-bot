# Sneaker Resale Bot

Proyecto de bot para detectar ofertas de zapatillas en Telegram, puntuar las mejores deals, guardar estadísticas en SQLite y mostrar un dashboard con Streamlit.

## Características

- Escucha mensajes en grupos de Telegram con Telethon
- Extrae links y detecta precios en varios formatos
- Calcula un score ponderado para destacar ofertas relevantes
- Guarda deals en `data/deals.db`
- Envía alertas por Telegram y email
- Dashboard en Streamlit con filtros, métricas y exportación CSV

## Requisitos

- Python 3.11+ recomendado
- Dependencias en `requirements.txt`

## Instalación

```bash
python -m pip install -r requirements.txt
```

## Configuración

Copia `.env.example` a `.env` y completa las variables:

```env
API_ID=...
API_HASH=...
CHAT_ID=...
EMAIL_USER=...
EMAIL_PASS=...
ALERT_MIN_SCORE=60
DATABASE_PATH=data/deals.db
TELETHON_SESSION=session
```

## Ejecución

Iniciar el bot:

```bash
python main.py
```

Iniciar el dashboard:

```bash
streamlit run dashboard.py
```

## Notas

- El bot ahora carga links existentes desde la base de datos para evitar duplicados entre reinicios.
- La base de datos usa WAL para mejor concurrencia.
- El dashboard incluye filtros, búsqueda, ranking de grupos y descarga CSV.
- Se agregó mantenimiento periódico para limpiar deals antiguos.
