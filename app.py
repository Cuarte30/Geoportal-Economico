import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium
from shapely.geometry import box
from shapely.validation import make_valid
import numpy as np
import tempfile
import zipfile
import os

st.set_page_config(
    page_title="Geoportal Económico | División Agropecuaria",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------------------------------------------
# BRANDING & ASESORAMIENTO
# -------------------------------------------------------------
LOGO_URL = "https://cdn-icons-png.flaticon.com/512/2933/2933902.png" 

st.sidebar.image(LOGO_URL, width=110)
st.sidebar.title("División Agropecuaria")
st.sidebar.caption("Soluciones en Agricultura de Precisión")
st.sidebar.markdown("---")

st.sidebar.subheader("👨‍🌾 Soporte y Asesoramiento")
st.sidebar.markdown("""
**Ing. Agr. Rodrigo Díaz Bustos**  
📞 **Tel:** +54 9 3472 556111  
📍 Noetinger, Córdoba  
✉️ rodrigodb9610@gmail.com
""")
st.sidebar.markdown("---")

# -------------------------------------------------------------
# CONFIGURACIÓN DEL CAMPO
# -------------------------------------------------------------
st.sidebar.header("📁 Organización del Campo")
productor = st.sidebar.text_input("Productor / Empresa", "División Agropecuaria")
establecimiento = st.sidebar.text_input("Establecimiento / Campo", "El OmBú")
lote_nombre = st.sidebar.text_input("Lote / Campaña", "Lote 12 - Campaña 25/26")

st.sidebar.markdown("---")
st.sidebar.header("🌱 Cultivo y Manejo Financiero")

tipo_cultivo = st.sidebar.selectbox("Seleccionar Cultivo", ["Soja", "Maíz", "Trigo"])

precio_grano = st.sidebar.number_input(
    "Precio Comercialización (USD/tn)", 
    value=320.0 if tipo_cultivo == "Soja" else (180.0 if tipo_cultivo == "Maíz" else 210.0)
)
costo_fijo = st.sidebar.number_input("Costo Fijo (Labores, Agroquímicos, Arriendo) [USD/ha]", value=200.0)

st.sidebar.markdown("---")
st.sidebar.header("📤 Carga de Archivos Spatial")
uploaded_files = st.sidebar.file_uploader(
    "Subir archivos del Lote (.zip con SHP o múltiples .kml/.shp)", 
    type=["zip", "kml", "shp"], 
    accept_multiple_files=True
)

st.title("🌾 Geoportal Económico por Píxel (10x10m)")
st.markdown("**División Agropecuaria** | *Mapeo dinámico de atributos y unidades de monitores.*")

if uploaded_files:
    # 1. Leer todas las capas subidas
    gdfs = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for file in uploaded_files:
            if file.name.endswith('.zip'):
                zip_path = os.path.join(tmpdir, file.name)
                with open(zip_path, "wb") as f:
                    f.write(file.getbuffer())
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(tmpdir)
                for shp in [f for f in os.listdir(tmpdir) if f.endswith('.shp')]:
                    gdfs.append(gpd.read_file(os.path.join(tmpdir, shp)))
            elif file.name.endswith('.kml'):
                kml_path = os.path.join(tmpdir, file.name)
                with open(kml_path, "wb") as f:
                    f.write(kml_path)
                gdfs.append(gpd.read_file(kml_path, driver='KML'))

    # Unir todas las columnas disponibles en la interfaz
    todas_columnas = []
    for gdf in gdfs:
        todas_columnas.extend([c for c in gdf.columns if c != 'geometry'])
    todas_columnas = list(dict.fromkeys(todas_columnas)) # Eliminar duplicados

    st.subheader("⚙️ Mapeo Interactivo de Columnas y Unidades")
    st.info("Selecciona la columna del archivo que corresponde a cada parámetro y confirma su unidad.")

    col1, col2 = st.columns(2)

    with col1:
        # Columna de Rinde
        idx_rinde = next((i for i, c in enumerate(todas_columnas) if any(k in c.lower() for k in ['seco', 'rinde', 'masa', 'yield'])), 0)
        col_selected_rinde = st.selectbox("Columna de Rendimiento (Rinde):", todas_columnas, index=idx_rinde)

        # Configuración Semilla
        if tipo_cultivo == "Soja":
            pms_g = st.number_input("PMS Soja (gramos)", value=155.0)
            costo_semilla_kg = st.number_input("Costo Semilla Soja (USD/kg)", value=1.08)
            dist_surco = st.number_input("Distancia entre surcos (m)", value=0.42)
            
            modo_dosis_soja = st.radio("Semilla Soja", ["Dosis Variable (de Archivo)", "Dosis Fija Promedio"])
            if modo_dosis_soja == "Dosis Variable (de Archivo)":
                idx_sem = next((i for i, c in enumerate(todas_columnas) if any(k in c.lower() for k in ['prop', 'meta', 'dosis', 'sem'])), 0)
                col_selected_sem = st.selectbox("Columna Dosis Semilla Soja:", todas_columnas, index=idx_sem)
                unidad_sem = st.radio("Unidad en el Monitor (Semilla Soja):", ["Semillas / metro", "Miles de semillas / m (0.02 = 20 sem/m)", "Semillas / ha"])
            else:
                dosis_fija_sem_m = st.number_input("Dosis Fija Semillas/m Soja:", value=20.0)

        elif tipo_cultivo == "Maíz":
            costo_bolsa = st.number_input("Costo Bolsa Maíz [80k sem] (USD)", value=220.0)

        else: # Trigo
            costo_semilla_trigo_kg = st.number_input("Costo Semilla Trigo (USD/kg)", value=0.60)
            dosis_semilla_trigo_kg = st.number_input("Dosis Semilla Trigo (kg/ha)", value=120.0)

    with col2:
        # Configuración Fertilizantes
        if tipo_cultivo == "Soja":
            aplica_ferti_soja = st.checkbox("¿Aplica Fertilizante en Soja?", value=False)
            if aplica_ferti_soja:
                costo_ferti_soja_tn = st.number_input("Costo Fertilizante Soja (USD/tn)", value=650.0)
                modo_ferti_soja = st.radio("Fertilizante Soja", ["Dosis Variable (de Archivo)", "Dosis Fija (kg/ha)"])
                if modo_ferti_soja == "Dosis Variable (de Archivo)":
                    idx_ferti = next((i for i, c in enumerate(todas_columnas) if any(k in c.lower() for k in ['part', 'ferti', 'fosf', 'dosis'])), 0)
                    col_selected_ferti_soja = st.selectbox("Columna Fertilizante Soja:", todas_columnas, index=idx_ferti)

        elif tipo_cultivo == "Maíz":
            st.markdown("**Arrancador (Fósforo) / Nitrogenado (Urea):**")
            costo_arrancador_tn = st.number_input("Costo Arrancador (USD/tn)", value=750.0)
            costo_urea_tn = st.number_input("Costo Urea (USD/tn)", value=550.0)
            
            modo_urea = st.radio("Urea Maíz", ["Dosis Variable (de Archivo)", "Dosis Fija (kg/ha)"])
            if modo_urea == "Dosis Variable (de Archivo)":
                idx_urea = next((i for i, c in enumerate(todas_columnas) if any(k in c.lower() for k in ['part', 'urea', 'nitro', 'uan'])), 0)
                col_selected_urea = st.selectbox("Columna Dosis Urea:", todas_columnas, index=idx_urea)

    # Botón para confirmar y calcular
    if st.button("🚀 Calcular y Generar Mapa Económico", type="primary"):
        with st.spinner("Procesando geometrías, unificando unidades y generando grilla 10x10m..."):
            # Base Spatial
            base_gdf = gdfs[0].to_crs(epsg=32720)
            base_gdf['geometry'] = base_gdf['geometry'].apply(lambda geom: make_valid(geom) if not geom.is_valid else geom).buffer(0)
            
            # Grilla 10x10
            xmin, ymin, xmax, ymax = base_gdf.total_bounds
            grid_size = 10
            cols = np.arange(xmin, xmax, grid_size)
            rows = np.arange(ymin, ymax, grid_size)
            
            polygons = [box(x, y, x + grid_size, y + grid_size) for x in cols for y in rows]
            grid = gpd.GeoDataFrame({'geometry': polygons}, crs=base_gdf.crs)
            grid_clipped = gpd.clip(grid, base_gdf)
            
            # Spatial Join de todas las capas
            joined = grid_clipped.copy()
            for idx, gdf in enumerate(gdfs):
                gdf_utm = gdf.to_crs(epsg=32720)
                gdf_utm['geometry'] = gdf_utm['geometry'].apply(lambda geom: make_valid(geom) if not geom.is_valid else geom).buffer(0)
                joined = gpd.sjoin(joined, gdf_utm, how="left", predicate="intersects", rsuffix=f"_{idx}")

            # 1. CÁLCULO DE RINDE
            joined['Rinde_tn'] = pd.to_numeric(joined[col_selected_rinde].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)

            # 2. CÁLCULO SEGÚN CULTIVO
            if tipo_cultivo == "Soja":
                if modo_dosis_soja == "Dosis Variable (de Archivo)":
                    raw_sem = pd.to_numeric(joined[col_selected_sem].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                    
                    # Conversión flexible de unidades
                    if unidad_sem == "Miles de semillas / m (0.02 = 20 sem/m)":
                        joined['Sem_m'] = raw_sem * 1000.0
                    elif unidad_sem == "Semillas / ha":
                        joined['Sem_m'] = (raw_sem / 10000.0) * dist_surco
                    else:
                        joined['Sem_m'] = raw_sem
                else:
                    joined['Sem_m'] = dosis_fija_sem_m
                
                sem_ha = joined['Sem_m'] * (10000.0 / dist_surco)
                costo_sem_ha = (sem_ha * (pms_g / 1000.0) / 1000.0) * costo_semilla_kg
                costo_ferti_ha = 0.0
                
                ingreso_ha = joined['Rinde_tn'] * precio_grano
                margen_ha = ingreso_ha - costo_sem_ha - costo_fijo

            elif tipo_cultivo == "Maíz":
                costo_sem_ha = costo_bolsa
                
                if modo_urea == "Dosis Variable (de Archivo)":
                    raw_urea = pd.to_numeric(joined[col_selected_urea].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                    joined['Urea_kg'] = raw_urea
                else:
                    joined['Urea_kg'] = 200.0
                    
                costo_urea_ha = (joined['Urea_kg'] / 1000.0) * costo_urea_tn
                ingreso_ha = joined['Rinde_tn'] * precio_grano
                margen_ha = ingreso_ha - costo_sem_ha - costo_urea_ha - costo_fijo

            else: # Trigo
                costo_sem_ha = dosis_semilla_trigo_kg * costo_semilla_trigo_kg
                ingreso_ha = joined['Rinde_tn'] * precio_grano
                margen_ha = ingreso_ha - costo_sem_ha - costo_fijo

            joined['MargenUSD_ha'] = margen_ha.round(2)
            joined['IngresoUSD_ha'] = ingreso_ha.round(2)
            gdf_resultado = joined.to_crs(epsg=4326)

            st.success(f"Mapa generado con éxito | {productor} - {establecimiento} ({lote_nombre})")

            # Métricas
            c1, c2, c3 = st.columns(3)
            c1.metric("Margen Bruto Promedio", f"{gdf_resultado['MargenUSD_ha'].mean():.2f} USD/ha")
            c2.metric("Rendimiento Promedio", f"{gdf_resultado['Rinde_tn'].mean():.2f} tn/ha")
            c3.metric("Ingreso Promedio", f"{gdf_resultado['IngresoUSD_ha'].mean():.2f} USD/ha")

            # Visor Leaflet
            st.subheader("🗺️ Visor Geográfico de Margen Bruto (10x10m)")
            centro_lat = gdf_resultado.geometry.centroid.y.mean()
            centro_lon = gdf_resultado.geometry.centroid.x.mean()
            
            m = folium.Map(location=[centro_lat, centro_lon], zoom_start=15, tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", attr="Google Hybrid")
            
            v_min = float(gdf_resultado['MargenUSD_ha'].min())
            v_max = float(gdf_resultado['MargenUSD_ha'].max())
            rango = (v_max - v_min) if (v_max - v_min) > 0 else 1.0

            def get_color(val):
                pct = (val - v_min) / rango
                if pct < 0.5:
                    f = pct / 0.5
                    r = 231 + int((241 - 231) * f)
                    g = 76 + int((196 - 76) * f)
                    b = 60 + int((15 - 60) * f)
                else:
                    f = (pct - 0.5) / 0.5
                    r = 241 + int((39 - 241) * f)
                    g = 196 + int((174 - 196) * f)
                    b = 15 + int((96 - 15) * f)
                return f'#{r:02x}{g:02x}{b:02x}'

            folium.GeoJson(
                gdf_resultado,
                style_function=lambda feature: {
                    'fillColor': get_color(feature['properties']['MargenUSD_ha']),
                    'color': 'black',
                    'weight': 0.1,
                    'fillOpacity': 0.65
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=['Rinde_tn', 'IngresoUSD_ha', 'MargenUSD_ha'],
                    aliases=['Rinde (tn/ha):', 'Ingreso (USD/ha):', 'Margen Bruto (USD/ha):'],
                    localize=True
                )
            ).add_to(m)

            st_folium(m, width=1100, height=550)

else:
    st.info("👈 Sube los archivos del lote en el panel izquierdo para comenzar.")
