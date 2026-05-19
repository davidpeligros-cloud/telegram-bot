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
    show_favorites = st.checkbox("⭐ Mostrar solo favoritos", value=False)
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
                    from zoneinfo import ZoneInfo
                    madrid_tz = ZoneInfo("Europe/Madrid")
                    next_summary = datetime.fromisoformat(next_summary_str)
                    now_time = datetime.now(madrid_tz)
                    if next_summary > now_time:
                        diff = next_summary - now_time
                        hours = int(diff.total_seconds() // 3600)
                        minutes = int((diff.total_seconds() % 3600) // 60)
                        
                        st.metric(
                            "Próximo Resumen Diario", 
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

if "favorite" not in filtered.columns:
    filtered["favorite"] = 0
if show_favorites:
    filtered = filtered[filtered["favorite"] == 1]

stats_col1, stats_col2, stats_col3, stats_col4 = st.columns(4)
stats_col1.metric("Deals totales", len(filtered))
stats_col2.metric("Score medio", round(filtered["score"].mean() if not filtered.empty else 0, 1))
stats_col3.metric("Grupos únicos", filtered["group_name"].nunique())
stats_col4.metric("Mejor score", int(filtered["score"].max() if not filtered.empty else 0))

st.markdown("---")

# Crear pestañas principales
tab1, tab2 = st.tabs(["📈 Analíticas e Historial", "📦 Gestión de Envíos"])

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
    
    st.markdown("---")
    st.subheader("👟 Feed de Ofertas Cazadas")
    
    if filtered.empty:
        st.info("💡 No se han encontrado ofertas con los filtros actuales.")
    else:
        col_sort, col_limit = st.columns([2, 1])
        with col_sort:
            sort_by = st.selectbox("Ordenar feed por:", ["Más Recientes", "Mejor Score 🔥"])
        with col_limit:
            feed_limit = st.selectbox("Mostrar cantidad:", [12, 24, 48, 96], index=1)
            
        if sort_by == "Más Recientes":
            display_deals = filtered.sort_values(by="date", ascending=False)
        else:
            display_deals = filtered.sort_values(by="score", ascending=False)
            
        display_deals = display_deals.head(feed_limit)
        
        # Grid de 3 columnas
        cols = st.columns(3)
        for i, (_, row) in enumerate(display_deals.iterrows()):
            col = cols[i % 3]
            with col:
                with st.container():
                    img_path = row["image_path"]
                    if isinstance(img_path, str) and img_path.strip() and os.path.exists(img_path):
                        st.image(img_path, use_container_width=True)
                    else:
                        # Imagen de stock premium de zapatilla como fallback
                        st.image("https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&q=80", use_container_width=True)
                        
                    st.markdown(f"#### {row['product'][:45]}...")
                    st.write(f"🔥 Score: **{row['score']}** | 💰 Precio: **{row['price']}**")
                    st.write(f"📢 Grupo: *{row['group_name']}*")
                    st.write(f"📅 Fecha: `{row['date'].strftime('%d/%m/%Y %H:%M')}`")
                    
                    # Botones de Acción (Oferta + Favorito)
                    col_card1, col_card2 = st.columns([1.2, 1])
                    with col_card1:
                        st.markdown(f"[🛍️ Ir a la Oferta]({row['link']})")
                    with col_card2:
                        deal_id = int(row["id"])
                        is_fav = int(row.get("favorite") or 0) == 1
                        if is_fav:
                            if st.button("❤️ Guardado", key=f"fav_btn_{deal_id}", use_container_width=True):
                                db_manager.toggle_favorite(deal_id, 0)
                                st.rerun()
                        else:
                            if st.button("🖤 Favorito", key=f"fav_btn_{deal_id}", use_container_width=True):
                                db_manager.toggle_favorite(deal_id, 1)
                                st.rerun()
                    st.markdown("---")
                    
    st.markdown("---")
    csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Descargar CSV",
        data=csv,
        file_name="sneaker_deals.csv",
        mime="text/csv",
    )

with tab2:
    st.header("📦 Control de Stock y Reventa (Reselling)")
    
    # Obtener todos los envíos
    shipments = db_manager.get_all_shipments()
    shipments_list = [dict(s) for s in shipments]
    
    if not shipments_list:
        st.info("No tienes ningún pedido registrado todavía. ¡Usa el formulario de abajo para añadir uno!")
    else:
        shipments_df = pd.DataFrame(shipments_list)
        
        # Homologar estados antiguos a los nuevos para compatibilidad
        shipments_df["status"] = shipments_df["status"].replace({
            "Enviado": "En tránsito",
            "Recibido": "En Stock"
        })
        
        # Tipar datos
        shipments_df["purchase_price"] = pd.to_numeric(shipments_df["purchase_price"], errors="coerce").fillna(0.0)
        shipments_df["resell_price"] = pd.to_numeric(shipments_df["resell_price"], errors="coerce").fillna(0.0)
        shipments_df["fees"] = pd.to_numeric(shipments_df["fees"], errors="coerce").fillna(0.0)
        shipments_df["created_at"] = pd.to_datetime(shipments_df["created_at"], errors="coerce")
        shipments_df["sold_at"] = pd.to_datetime(shipments_df["sold_at"], errors="coerce")
        
        # Calcular inversiones y retornos individuales
        shipments_df["total_cost"] = shipments_df["purchase_price"] + shipments_df["fees"]
        shipments_df["profit"] = shipments_df["resell_price"] - shipments_df["total_cost"]
        shipments_df["roi"] = (shipments_df["profit"] / shipments_df["total_cost"] * 100).fillna(0.0)
        
        # --- CÁLCULO DE KPIs ---
        # 1. Total invertido histórico (Todas las compras)
        total_invested_all = shipments_df["total_cost"].sum()
        
        # 2. Stock Activo (Pedido, En tránsito, En reparto, En Stock)
        active_mask = shipments_df["status"] != "Vendido"
        stock_active_cost = shipments_df.loc[active_mask, "total_cost"].sum()
        stock_active_est_return = shipments_df.loc[active_mask, "resell_price"].sum()
        stock_active_unrealized_profit = stock_active_est_return - stock_active_cost
        
        # 3. Ventas Realizadas (Vendido)
        sold_mask = shipments_df["status"] == "Vendido"
        sold_count = sold_mask.sum()
        realized_profit = shipments_df.loc[sold_mask, "profit"].sum()
        realized_investment = shipments_df.loc[sold_mask, "total_cost"].sum()
        realized_roi = (realized_profit / realized_investment * 100) if realized_investment > 0 else 0.0
        
        # 4. Tiempo medio en venta (Hold time)
        hold_days = (shipments_df["sold_at"] - shipments_df["created_at"]).dt.days
        avg_hold_days = hold_days[sold_mask].mean()
        
        # --- RENDER KPIs ---
        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        col_kpi1.metric(
            "💰 Valor de Stock Activo", 
            f"{stock_active_cost:,.2f} €", 
            help="Dinero invertido en zapatillas en stock o en camino (Precio Compra + Tasas)."
        )
        col_kpi2.metric(
            "📈 Ganancia Estimada (Stock)", 
            f"{stock_active_unrealized_profit:,.2f} €", 
            delta=f"+{stock_active_unrealized_profit:,.2f} €",
            help="Beneficio neto estimado que obtendrás cuando vendas todo tu stock actual."
        )
        
        profit_color = "normal" if realized_profit >= 0 else "inverse"
        col_kpi3.metric(
            "💵 Beneficio Realizado (Ventas)", 
            f"{realized_profit:,.2f} €", 
            delta=f"+{realized_profit:,.2f} €" if realized_profit >= 0 else f"{realized_profit:,.2f} €",
            delta_color=profit_color,
            help="Dinero neto real que ya has ganado en mano con tus ventas completadas."
        )
        
        col_kpi4, col_kpi5, col_kpi6 = st.columns(3)
        col_kpi4.metric(
            "🛍️ Inversión Total Histórica", 
            f"{total_invested_all:,.2f} €", 
            help="Capital total que ha pasado por el bot (compras activas + vendidas)."
        )
        col_kpi5.metric(
            "🎯 ROI Realizado en Ventas", 
            f"{realized_roi:.1f} %",
            help="Retorno de inversión promedio de tus ventas cerradas."
        )
        if not pd.isna(avg_hold_days):
            col_kpi6.metric(
                "⏳ Días Medios en Stock", 
                f"{avg_hold_days:.1f} días",
                help="Tiempo promedio que tardas en vender una zapatilla desde que la registras hasta que pasa a Vendido."
            )
        else:
            col_kpi6.metric("⏳ Días Medios en Stock", "N/A", help="Se calculará cuando tengas al menos un artículo Vendido.")
            
        st.markdown("---")
        
        # --- SECCIÓN GRÁFICOS ---
        col_chart_left, col_chart_right = st.columns(2)
        
        with col_chart_left:
            st.subheader("📊 Distribución por Estado")
            status_counts = shipments_df["status"].value_counts().reset_index()
            status_counts.columns = ["Estado", "Cantidad"]
            fig_donut = px.pie(
                status_counts, 
                values="Cantidad", 
                names="Estado", 
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_donut.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=250)
            st.plotly_chart(fig_donut, use_container_width=True)
            
        with col_chart_right:
            st.subheader("💵 Rentabilidad por Producto")
            # Coger las 10 últimas compras para el gráfico
            rent_df = shipments_df.head(10).copy()
            fig_bar = px.bar(
                rent_df, 
                x="product_name", 
                y="profit", 
                color="status",
                labels={"product_name": "Producto", "profit": "Beneficio (€)"},
                title="Beneficio Esperado/Realizado (Top 10 Recientes)",
                color_discrete_map={
                    "Pedido": "#FFE082",
                    "En tránsito": "#90CAF9",
                    "En reparto": "#CE93D8",
                    "En Stock": "#A5D6A7",
                    "Vendido": "#81C784"
                }
            )
            fig_bar.update_layout(xaxis_tickangle=-30, height=250, margin=dict(t=20, b=10, l=10, r=10))
            st.plotly_chart(fig_bar, use_container_width=True)
            
        st.markdown("---")

    # Formulario para agregar un envío
    with st.expander("➕ Registrar Nueva Compra/Envío"):
        with st.form("new_shipment_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                ship_product = st.text_input("Nombre del Producto (ej: Nike Dunk Low Grey Fog)", value="")
                ship_carrier = st.selectbox("Transportista", ["Correos", "Correos Express", "SEUR", "DHL", "GLS", "UPS", "FedEx", "Mondial Relay / InPost", "Nacex", "Otro"])
                ship_purchase = st.number_input("Precio de Compra (€)", min_value=0.0, value=0.0, step=1.0)
                ship_size = st.text_input("Talla (ej: 42.5, 9 US)", value="", placeholder="Talla")
            with col2:
                ship_tracking = st.text_input("Nº de Seguimiento / Tracking", value="")
                ship_resell = st.number_input("Precio Estimado de Reventa (€)", min_value=0.0, value=0.0, step=1.0)
                ship_fees = st.number_input("Tasas / Envío / Comisiones (€)", min_value=0.0, value=0.0, step=1.0)
                ship_store = st.text_input("Tienda de Compra", value="", placeholder="SNKRS, Confirmed, etc.")
                
            ship_notes = st.text_area("Notas / Enlace de compra", value="", placeholder="Detalles de compra...")
                
            submitted = st.form_submit_button("Guardar Envío en Inventario")
            if submitted:
                if not ship_product or not ship_tracking:
                    st.error("Por favor, introduce el nombre del producto y el número de seguimiento.")
                else:
                    saved = db_manager.save_shipment(
                        product_name=ship_product,
                        carrier=ship_carrier,
                        tracking_number=ship_tracking,
                        status="Pedido",
                        notes=ship_notes,
                        purchase_price=ship_purchase,
                        resell_price=ship_resell,
                        fees=ship_fees,
                        size=ship_size if ship_size.strip() else None,
                        store=ship_store if ship_store.strip() else None
                    )
                    if saved:
                        st.success(f"¡Compra de '{ship_product}' registrada correctamente!")
                        st.rerun()
                    else:
                        st.error("Error al guardar el envío en la base de datos.")

    if shipments_list:
        # Generar enlaces oficiales de seguimiento automáticos en el DataFrame
        def get_tracking_link(row):
            carrier = str(row["carrier"]).lower()
            tracking = row["tracking_number"]
            if "correosexpress" in carrier or "correos express" in carrier:
                return f"https://www.correosexpress.com/web/correosexpress/consultanos?numEnvio={tracking}"
            elif "correos" in carrier:
                return f"https://www.correos.es/es/es/herramientas/localizador/detalle?cod_envio={tracking}"
            elif "seur" in carrier:
                return f"https://www.seur.com/livetracking/pages/seguimiento-online-busqueda.do?excode={tracking}"
            elif "dhl" in carrier:
                return f"https://www.dhl.com/es-es/home/tracking/tracking-express.html?submit=1&tracking-id={tracking}"
            elif "gls" in carrier:
                return f"https://www.gls-spain.es/es/recibir-paquetes/seguimiento-envio/?pcode={tracking}"
            elif "ups" in carrier:
                return f"https://www.ups.com/track?loc=es_ES&requester=ST&tracknum={tracking}"
            elif "fedex" in carrier:
                return f"https://www.fedex.com/apps/fedextrack/?tracknumbers={tracking}"
            elif "mondial" in carrier or "inpost" in carrier:
                return f"https://www.inpost.es/seguimiento-de-envios/?trackingNumber={tracking}"
            elif "nacex" in carrier:
                return f"https://www.nacex.es/seguimientoDetalle.xhtml?convenio=1&estado=1&referencia={tracking}"
            return ""
            
        shipments_df["Enlace de Rastreo"] = shipments_df.apply(get_tracking_link, axis=1)
        
        st.subheader("📋 Tu Inventario y Pedidos Activos")
        
        # Filtros de tabla
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            filter_status = st.selectbox("Filtrar por Estado", ["Todos", "Activos", "Pedido", "En tránsito", "En reparto", "En Stock", "Vendido"])
        with col_f2:
            store_options = ["Todos"] + sorted(list(shipments_df["store"].dropna().unique()))
            filter_store = st.selectbox("Filtrar por Tienda", store_options)
        with col_f3:
            size_options = ["Todos"] + sorted(list(shipments_df["size"].dropna().unique()))
            filter_size = st.selectbox("Filtrar por Talla", size_options)
            
        # Aplicar filtros al feed visual
        disp_df = shipments_df.copy()
        if filter_status == "Activos":
            disp_df = disp_df[disp_df["status"] != "Vendido"]
        elif filter_status != "Todos":
            disp_df = disp_df[disp_df["status"] == filter_status]
            
        if filter_store != "Todos":
            disp_df = disp_df[disp_df["store"] == filter_store]
            
        if filter_size != "Todos":
            disp_df = disp_df[disp_df["size"] == filter_size]
            
        # Mostrar cada envío activo en tarjetas estilizadas
        if disp_df.empty:
            st.info("No hay pedidos que coincidan con los filtros seleccionados.")
        else:
            for idx, row in disp_df.iterrows():
                ship_id = row["id"]
                ship_name = row["product_name"]
                carrier = row["carrier"]
                tracking = row["tracking_number"]
                status = row["status"]
                notes = row["notes"] or "Sin notas adicionales."
                track_url = row["Enlace de Rastreo"]
                size_val = row["size"] or "N/A"
                store_val = row["store"] or "Desconocida"
                sold_plat = row["sold_platform"]
                sold_dt_val = row["sold_at"]
                
                # Formato estético del estado
                status_emoji = "⏳"
                if status == "En tránsito":
                    status_emoji = "🚚"
                elif status == "En reparto":
                    status_emoji = "🛵"
                elif status == "En Stock":
                    status_emoji = "👟"
                elif status == "Vendido":
                    status_emoji = "✅"
                    
                # Caja contenedora
                with st.container():
                    st.markdown(f"### {status_emoji} {ship_name}")
                    col_info, col_fin, col_actions = st.columns([2, 1.5, 1.5])
                    
                    with col_info:
                        st.markdown(f"📏 **Talla:** `{size_val}` | 🏪 **Tienda:** `{store_val}`")
                        st.write(f"🚚 **{carrier}:** `{tracking}`")
                        if track_url:
                            st.markdown(f"[🔗 Enlace Oficial de Seguimiento ({carrier})]({track_url})")
                        st.write(f"*Notas:* {notes}")
                        if status == "Vendido" and sold_plat:
                            st.markdown(f"🤝 **Vendido en:** `{sold_plat}`")
                            if sold_dt_val:
                                st.write(f"📅 **Fecha venta:** `{pd.to_datetime(sold_dt_val).strftime('%d/%m/%Y %H:%M')}`")
                                
                    with col_fin:
                        st.write("**📊 Rendimiento:**")
                        cost = float(row.get("purchase_price") or 0.0)
                        r_fees = float(row.get("fees") or 0.0)
                        resell = float(row.get("resell_price") or 0.0)
                        inv = cost + r_fees
                        profit = resell - inv
                        roi = (profit / inv * 100) if inv > 0 else 0.0
                        
                        st.write(f"💵 Inversión: `{inv:,.2f} €` (`{cost:.2f}`+`{r_fees:.2f}` tasas)")
                        if status == "Vendido":
                            st.write(f"💵 Venta Realizada: `{resell:,.2f} €`")
                            st.markdown(f"💰 Beneficio Neto: :green[{profit:+,.2f} €] (ROI: `{roi:+.1f}%`) ")
                        else:
                            st.write(f"📈 Reventa Est.: `{resell:,.2f} €`")
                            profit_color = "green" if profit >= 0 else "red"
                            st.markdown(f"💰 Ben. Estimado: :{profit_color}[{profit:+,.2f} €] (ROI: `{roi:+.1f}%`) ")
                            
                    with col_actions:
                        # Expander para editar todos los detalles de este pedido en caliente
                        with st.expander("✏️ Editar Detalles"):
                            with st.form(f"edit_form_{ship_id}"):
                                edit_status = st.selectbox(
                                    "Estado", 
                                    ["Pedido", "En tránsito", "En reparto", "En Stock", "Vendido"], 
                                    index=["Pedido", "En tránsito", "En reparto", "En Stock", "Vendido"].index(status),
                                    key=f"edit_status_sel_{ship_id}"
                                )
                                edit_carrier = st.selectbox(
                                    "Transportista", 
                                    ["Correos", "Correos Express", "SEUR", "DHL", "GLS", "UPS", "FedEx", "Mondial Relay / InPost", "Nacex", "Otro"],
                                    index=["Correos", "Correos Express", "SEUR", "DHL", "GLS", "UPS", "FedEx", "Mondial Relay / InPost", "Nacex", "Otro"].index(carrier) if carrier in ["Correos", "Correos Express", "SEUR", "DHL", "GLS", "UPS", "FedEx", "Mondial Relay / InPost", "Nacex", "Otro"] else 0
                                )
                                edit_tracking = st.text_input("Tracking", value=tracking)
                                edit_size = st.text_input("Talla", value=row["size"] or "")
                                edit_store = st.text_input("Tienda", value=row["store"] or "")
                                edit_purchase = st.number_input("Compra (€)", min_value=0.0, value=cost)
                                edit_fees = st.number_input("Tasas (€)", min_value=0.0, value=r_fees)
                                edit_resell = st.number_input("Reventa (€)", min_value=0.0, value=resell)
                                
                                # Campos condicionales si el estado es Vendido
                                edit_sold_plat = None
                                if edit_status == "Vendido":
                                    edit_sold_plat = st.selectbox(
                                        "Plataforma de Venta",
                                        ["StockX", "alias", "Vinted", "Wallapop", "KLEKT", "eBay", "En mano", "Otra"],
                                        index=["StockX", "alias", "Vinted", "Wallapop", "KLEKT", "eBay", "En mano", "Otra"].index(sold_plat) if sold_plat in ["StockX", "alias", "Vinted", "Wallapop", "KLEKT", "eBay", "En mano", "Otra"] else 6
                                    )
                                    
                                edit_notes = st.text_area("Notas", value=row["notes"] or "")
                                
                                save_edit = st.form_submit_button("Guardar Cambios")
                                if save_edit:
                                    success = db_manager.update_shipment_status(
                                        shipment_id=ship_id,
                                        new_status=edit_status,
                                        notes=edit_notes,
                                        sold_platform=edit_sold_plat,
                                        size=edit_size if edit_size.strip() else "",
                                        store=edit_store if edit_store.strip() else "",
                                        purchase_price=edit_purchase,
                                        fees=edit_fees,
                                        resell_price=edit_resell,
                                        tracking_number=edit_tracking,
                                        carrier=edit_carrier
                                    )
                                    if success:
                                        st.success("¡Pedido actualizado con éxito!")
                                        st.rerun()
                                    else:
                                        st.error("Error al actualizar el pedido.")
                                        
                        if st.button("🗑️ Eliminar Envío", key=f"del_{ship_id}", use_container_width=True):
                            if db_manager.delete_shipment(ship_id):
                                st.warning("Envío eliminado.")
                                st.rerun()
                    st.markdown("---")
            
            # Botón para descargar el inventario completo en Excel/CSV
            export_df = shipments_df.drop(columns=["Enlace de Rastreo", "total_cost", "profit", "roi"], errors="ignore")
            csv_data = export_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Exportar Inventario Completo a CSV",
                data=csv_data,
                file_name="inventario_sneaker_bot.csv",
                mime="text/csv",
                use_container_width=True
            )

st.markdown("---")

with st.expander("Descripción del flujo de datos"):
    st.write(
        "Telegram Groups → Telethon Listener → Filtro / Score → SQLite Database "
        "→ Telegram + Email Alerts → Dashboard Streamlit"
    )
