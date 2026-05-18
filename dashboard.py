import sqlite3
import os
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
import plotly.express as px

from database import DealDatabase
db_manager = DealDatabase("data/deals.db")

st.set_page_config(page_title="Sneaker Bot Dashboard", layout="wide")
st.title("🔥 Sneaker Bot Dashboard")


@st.cache_data
def load_deals(db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        df = pd.read_sql_query("SELECT * FROM deals ORDER BY date DESC", conn)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame(
            columns=[
                "id",
                "product",
                "link",
                "price",
                "score",
                "group_name",
                "date",
                "message_id",
                "user_id",
                "created_at",
            ]
        )
    finally:
        conn.close()


df = load_deals("data/deals.db")

with st.sidebar:
    st.header("Filtros")
    search_text = st.text_input("Buscar keyword", value="")
    min_score = st.slider("Score mínimo", 0, 200, 60)
    last_days = st.selectbox("Últimos días", [7, 14, 30, 90, 180], index=2)
    group_options = sorted(df["group_name"].dropna().unique().tolist()) if not df.empty else []
    selected_groups = st.multiselect("Grupos", group_options, default=group_options)
    date_range = st.date_input(
        "Rango de fechas",
        [datetime.now().date() - timedelta(days=last_days), datetime.now().date()],
    )
    st.markdown("---")
    
    # Mostrar cantidad de envíos activos
    try:
        active_count = len(db_manager.get_active_shipments())
        if active_count > 0:
            st.metric("📦 Envíos en camino", f"{active_count} activos")
        else:
            st.metric("📦 Envíos en camino", "Ninguno")
    except Exception:
        pass
        
    st.markdown("---")
    
    # Mostrar cuenta atrás del próximo resumen bisemanal
    next_summary_path = "data/next_summary.txt"
    if os.path.exists(next_summary_path):
        try:
            with open(next_summary_path, "r") as f:
                next_summary_str = f.read().strip()
                if next_summary_str:
                    next_summary = datetime.fromisoformat(next_summary_str)
                    now_time = datetime.now()
                    if next_summary > now_time:
                        diff = next_summary - now_time
                        hours = int(diff.total_seconds() // 3600)
                        minutes = int((diff.total_seconds() % 3600) // 60)
                        
                        st.metric(
                            "Próximo Resumen Bisemanal", 
                            f"{hours}h {minutes}m", 
                            help=f"Programado para el {next_summary.strftime('%d/%m/%Y %H:%M')}"
                        )
                    else:
                        st.info("🔄 Procesando resumen actual...")
        except Exception:
            pass
            
    st.markdown(
        "[Actualizar datos](#)  \n*Los datos se cargan automáticamente al iniciar el dashboard.*"
    )

if df.empty:
    st.warning("No hay datos disponibles todavía. Ejecuta el bot y recarga esta página.")
    st.stop()

if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_date, end_date = date_range
elif isinstance(date_range, (list, tuple)) and len(date_range) == 1:
    start_date = date_range[0]
    end_date = date_range[0]
else:
    start_date = date_range
    end_date = date_range

filtered = df.copy()
filtered = filtered[filtered["score"] >= min_score]
if "date" in filtered.columns and not filtered.empty:
    filtered = filtered[filtered["date"].dt.date >= start_date]
    filtered = filtered[filtered["date"].dt.date <= end_date]
if search_text:
    filtered = filtered[
        filtered["product"].str.contains(search_text, case=False, na=False)
        | filtered["link"].str.contains(search_text, case=False, na=False)
    ]
if selected_groups:
    filtered = filtered[filtered["group_name"].isin(selected_groups)]

stats_col1, stats_col2, stats_col3, stats_col4 = st.columns(4)
stats_col1.metric("Deals totales", len(filtered))
stats_col2.metric("Score medio", round(filtered["score"].mean() if not filtered.empty else 0, 1))
stats_col3.metric("Grupos únicos", filtered["group_name"].nunique())
stats_col4.metric("Mejor score", int(filtered["score"].max() if not filtered.empty else 0))

st.markdown("---")

# Crear pestañas principales
tab1, tab2, tab3 = st.tabs(["📈 Analíticas e Historial", "🎨 Galería de Ofertas", "📦 Gestión de Envíos"])

with tab1:
    st.subheader("📈 Evolución de Deals (Últimos Días)")
    deals_by_date = filtered.copy()
    deals_by_date['date_only'] = deals_by_date['date'].dt.date
    daily_deals = deals_by_date.groupby('date_only').size().reset_index(name='count')
    if not daily_deals.empty:
        fig_line = px.line(daily_deals, x='date_only', y='count', markers=True, title="Deals Cazadas por Día", 
                           labels={'date_only': 'Fecha', 'count': 'Número de Deals'},
                           line_shape='spline')
        fig_line.update_traces(line_color='#FF4B4B')
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("No hay datos suficientes para mostrar evolución temporal.")
    
    col_charts1, col_charts2 = st.columns(2)
    
    with col_charts1:
        st.subheader("🏆 Top grupos")
        top_groups = filtered.groupby("group_name").size().reset_index(name='count').sort_values('count', ascending=False).head(10)
        if not top_groups.empty:
            fig_groups = px.bar(top_groups, x='group_name', y='count',
                                labels={'group_name': 'Grupo', 'count': 'Deals'},
                                color='count', color_continuous_scale='Reds')
            st.plotly_chart(fig_groups, use_container_width=True)
    
    with col_charts2:
        st.subheader("🎯 Distribución de scores")
        if not filtered.empty:
            fig_hist = px.histogram(filtered, x='score', nbins=20,
                                    labels={'score': 'Score'}, color_discrete_sequence=['#FF4B4B'])
            st.plotly_chart(fig_hist, use_container_width=True)
    
    st.subheader("🔥 Mejores deals")
    top_deals = filtered.sort_values(by="score", ascending=False)
    st.dataframe(
        top_deals[["score", "price", "group_name", "date", "product", "link"]].head(25),
        column_config={
            "link": st.column_config.LinkColumn("🛍️ Enlace Directo", display_text="Ver Oferta"),
            "score": "🔥 Score",
            "price": "💰 Precio",
            "group_name": "📢 Grupo",
            "date": "📅 Fecha",
            "product": "👟 Producto"
        },
        use_container_width=True,
        hide_index=True,
    )
    
    st.markdown("---")
    
    st.subheader("📦 Todas las deals")
    st.dataframe(
        filtered[["date", "score", "price", "group_name", "product", "link"]].reset_index(drop=True),
        column_config={
            "link": st.column_config.LinkColumn("🛍️ Enlace Directo", display_text="Ver Oferta"),
            "score": "🔥 Score",
            "price": "💰 Precio",
            "group_name": "📢 Grupo",
            "date": "📅 Fecha",
            "product": "👟 Producto"
        },
        use_container_width=True,
        hide_index=True,
    )
    
    csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Descargar CSV",
        data=csv,
        file_name="sneaker_deals.csv",
        mime="text/csv",
    )

with tab2:
    st.subheader("🎨 Galería Visual de Ofertas")
    
    # Filtrar solo ofertas que tengan imagen
    deals_with_img = filtered[filtered["image_path"].notna() & (filtered["image_path"] != "")]
    
    if deals_with_img.empty:
        st.info("💡 Las imágenes de las ofertas se descargarán automáticamente cuando el bot reciba mensajes con foto en Telegram. De momento no hay ninguna foto registrada.")
    else:
        # Mostrar en cuadrícula de 3 columnas
        cols = st.columns(3)
        for i, (_, row) in enumerate(deals_with_img.head(21).iterrows()):
            col = cols[i % 3]
            with col:
                with st.container():
                    img_path = row["image_path"]
                    # Verificar si existe el archivo
                    if os.path.exists(img_path):
                        st.image(img_path, use_container_width=True)
                    else:
                        st.info("Imagen no disponible localmente")
                    st.markdown(f"#### {row['product'][:40]}...")
                    st.write(f"🔥 Score: **{row['score']}** | 💰 Precio: **{row['price']}**")
                    st.write(f"📢 Grupo: *{row['group_name']}*")
                    st.markdown(f"[🛍️ Ir a la Oferta]({row['link']})")
                    st.markdown("---")

with tab3:
    st.header("📦 Gestión de Envíos y Compras")
    
    # Formulario para agregar un envío
    with st.expander("➕ Registrar Nueva Compra/Envío"):
        with st.form("new_shipment_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                ship_product = st.text_input("Nombre del Producto (ej: Nike Jordan 4 Military)", value="")
                ship_carrier = st.selectbox("Transportista", ["Correos", "Correos Express", "SEUR", "DHL", "Otro"])
            with col2:
                ship_tracking = st.text_input("Nº de Seguimiento / Tracking", value="")
                ship_notes = st.text_area("Notas / Enlace de compra", value="", placeholder="Talla, precio, etc.")
                
            submitted = st.form_submit_button("Guardar Envío")
            if submitted:
                if not ship_product or not ship_tracking:
                    st.error("Por favor, introduce el nombre del producto y el número de seguimiento.")
                else:
                    saved = db_manager.save_shipment(
                        product_name=ship_product,
                        carrier=ship_carrier,
                        tracking_number=ship_tracking,
                        status="Pedido",
                        notes=ship_notes
                    )
                    if saved:
                        st.success(f"¡Envío de '{ship_product}' registrado correctamente!")
                        st.rerun()
                    else:
                        st.error("Error al guardar el envío en la base de datos.")
                        
    # Obtener envíos
    shipments = db_manager.get_all_shipments()
    if not shipments:
        st.info("No tienes ningún envío registrado todavía. ¡Usa el formulario de arriba para añadir uno!")
    else:
        # Convertir a DataFrame para mostrarlo limpio
        shipments_df = pd.DataFrame([dict(s) for s in shipments])
        
        # Generar enlaces oficiales de seguimiento automáticos en el DataFrame
        def get_tracking_link(row):
            carrier = row["carrier"].lower()
            tracking = row["tracking_number"]
            if "correosexpress" in carrier or "correos express" in carrier:
                return f"https://www.correosexpress.com/web/correosexpress/consultanos?numEnvio={tracking}"
            elif "correos" in carrier:
                return f"https://www.correos.es/es/es/herramientas/localizador/detalle?cod_envio={tracking}"
            elif "seur" in carrier:
                return f"https://www.seur.com/livetracking/pages/seguimiento-online-busqueda.do?excode={tracking}"
            elif "dhl" in carrier:
                return f"https://www.dhl.com/es-es/home/tracking/tracking-express.html?submit=1&tracking-id={tracking}"
            return ""
            
        shipments_df["Enlace de Rastreo"] = shipments_df.apply(get_tracking_link, axis=1)
        
        st.subheader("📋 Estado Actual de tus Envíos")
        
        # Mostraremos cada envío activo de forma muy visual en una lista, permitiendo actualizar o borrar
        for idx, row in shipments_df.iterrows():
            ship_id = row["id"]
            ship_name = row["product_name"]
            carrier = row["carrier"]
            tracking = row["tracking_number"]
            status = row["status"]
            notes = row["notes"] or "Sin notas."
            track_url = row["Enlace de Rastreo"]
            
            # Formato estético del estado
            status_emoji = "⏳"
            if status == "Enviado":
                status_emoji = "🚚"
            elif status == "En reparto":
                status_emoji = "🛵"
            elif status == "Recibido":
                status_emoji = "✅"
                
            # Tarjeta de envío
            with st.container():
                st.markdown(f"### {status_emoji} {ship_name} ({carrier})")
                col_info, col_actions = st.columns([3, 2])
                with col_info:
                    st.write(f"**Nº Seguimiento:** `{tracking}`")
                    st.write(f"**Estado actual:** `{status}`")
                    st.write(f"*Notas:* {notes}")
                    if track_url:
                        st.markdown(f"[🔗 Enlace Oficial de Rastreo ({carrier})]({track_url})")
                with col_actions:
                    new_status = st.selectbox(
                        "Actualizar Estado", 
                        ["Pedido", "Enviado", "En reparto", "Recibido"], 
                        index=["Pedido", "Enviado", "En reparto", "Recibido"].index(status),
                        key=f"status_{ship_id}"
                    )
                    
                    # Botón para actualizar el estado si ha cambiado
                    if new_status != status:
                        if db_manager.update_shipment_status(ship_id, new_status):
                            st.success(f"¡Estado actualizado a {new_status}!")
                            st.rerun()
                            
                    if st.button("🗑️ Eliminar Envío", key=f"del_{ship_id}"):
                        if db_manager.delete_shipment(ship_id):
                            st.warning("Envío eliminado.")
                            st.rerun()
                            
            st.markdown("---")

st.markdown("---")

with st.expander("Descripción del flujo de datos"):
    st.write(
        "Telegram Groups → Telethon Listener → Filtro / Score → SQLite Database "
        "→ Telegram + Email Alerts → Dashboard Streamlit"
    )
