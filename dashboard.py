import sqlite3
import os
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
import plotly.express as px

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
    use_container_width=True,
)

st.markdown("---")

st.subheader("📦 Todas las deals")
st.dataframe(
    filtered[["date", "score", "price", "group_name", "product", "link"]].reset_index(drop=True),
    use_container_width=True,
)

csv = filtered.to_csv(index=False).encode("utf-8")
st.download_button(
    label="📥 Descargar CSV",
    data=csv,
    file_name="sneaker_deals.csv",
    mime="text/csv",
)

with st.expander("Descripción del flujo de datos"):
    st.write(
        "Telegram Groups → Telethon Listener → Filtro / Score → SQLite Database "
        "→ Telegram + Email Alerts → Dashboard Streamlit"
    )
