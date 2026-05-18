#!/bin/bash
# start.sh - Script de inicio para Railway

# Crear la carpeta data si no existe (importante para el Volumen de Railway)
mkdir -p data

echo "Iniciando el Sneaker Bot en segundo plano..."
# Ejecutamos el bot en segundo plano
python main.py &

echo "Iniciando el Dashboard de Streamlit..."
# Ejecutamos Streamlit en primer plano en el puerto que nos asigne Railway
python -m streamlit run dashboard.py --server.port $PORT --server.address 0.0.0.0
