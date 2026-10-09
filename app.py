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
    page_title="Geoportal Económico Agrícola",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🌾 Geoportal Económico por Píxel (10x10m)")
st.markdown("Cálculo y gestión de Margen Bruto espacial para la red de productores.")

# Sidebar - Organización
st.sidebar.header("📁 Organización del Campo")
productor = st.sidebar.text_input("Nombre del Productor / Empresa", "Productor Ejemplo")
establecimiento = st.sidebar.text_input("Establecimiento / Campo", "El OmBú")
lote_nombre = st.sidebar.text_input("Nombre del Lote / Cultivo", "Norte - Soja 25/26")

st.sidebar.markdown("---")
st.sidebar.header("💰 Parámetros Financieros")

tipo_cultivo = st.sidebar.selectbox("Cultivo", ["Soja", "Maíz"])

precio_grano = st.sidebar.number_input("Precio Grano (USD/tn)", value=320.0 if tipo_cultivo == "Soja" else 180.0)
costo_fijo = st.sidebar.number_input("Costo Fijo (USD/ha)", value=200.0)

if tipo_cultivo == "Soja":
    costo_semilla_kg = st.sidebar.number_input("Costo Semilla (USD/kg)", value=1.08)
    pms_g = st.sidebar.number_input("Peso 1000 Semillas (gramos)", value=155.0)
    dist_surco = st.sidebar.number_input("Distancia entre surcos (m)", value=0.42)
    
    modo_dosis = st.sidebar.radio("Modo Dosis Semilla", ["Buscar en SHP (Variable)", "Dosis Fija Promedio"])
    if modo_dosis == "Dosis Fija Promedio":
        dosis_fija_sem_m = st.sidebar.number_input("Semillas por metro (fija)", value=20.0)
else:
    costo_bolsa = st.sidebar.number_input("Costo Bolsa Semilla (USD)", value=220.0)
    costo_urea_tn = st.sidebar.number_input("Costo Urea (USD/tn)", value=550.0)

st.sidebar.markdown("---")
st.sidebar.header("📤 Carga de Archivos Spatial")
uploaded_file = st.sidebar.file_uploader("Subir Mapa de Rinde (.zip con SHP o .kml)", type=["zip", "kml"])

def procesar_mapa_economico(gdf_input):
    gdf_utm = gdf_input.to_crs(epsg=32720)
    
    # Corregir geometrías
    gdf_utm['geometry'] = gdf_utm['geometry'].apply(lambda geom: make_valid(geom) if not geom.is_valid else geom)
    gdf_utm['geometry'] = gdf_utm['geometry'].buffer(0)
    
    # Crear Grilla 10x10m
    xmin, ymin, xmax, ymax = gdf_utm.total_bounds
    grid_size = 10
    
    cols = np.arange(xmin, xmax, grid_size)
    rows = np.arange(ymin, ymax, grid_size)
    
    polygons = [box(x, y, x + grid_size, y + grid_size) for x in cols for y in rows]
    grid = gpd.GeoDataFrame({'geometry': polygons}, crs=gdf_utm.crs)
    
    grid_clipped = gpd.clip(grid, gdf_utm)
    joined = gpd.sjoin(grid_clipped, gdf_utm, how="inner", predicate="intersects")
    
    # Detectar rinde (_seco_Masa)
    col_rinde_matches = [c for c in joined.columns if any(k in c.lower() for k in ['seco', 'rinde', 'masa', 'yield'])]
    col_rinde = col_rinde_matches[0] if col_rinde_matches else joined.columns[0]
    
    joined['Rinde_tn'] = pd.to_numeric(joined[col_rinde].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
    
    if tipo_cultivo == "Soja":
        if modo_dosis == "Buscar en SHP (Variable)":
            col_dens_matches = [c for c in joined.columns if any(k in c.lower() for k in ['prop', 'meta', 'dosis', 'cant', 'sem'])]
            if col_dens_matches:
                col_dens = col_dens_matches[0]
                dens_val = pd.to_numeric(joined[col_dens].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
                joined['Dens_m'] = np.where(dens_val < 1, dens_val * 1000, dens_val)
            else:
                joined['Dens_m'] = 20.0
        else:
            joined['Dens_m'] = dosis_fija_sem_m
        
        sem_ha = joined['Dens_m'] * (10000 / dist_surco)
        kg_sem_ha = sem_ha * (pms_g / 1000) / 1000
        costo_sem_ha = kg_sem_ha * costo_semilla_kg
        ingreso_ha = joined['Rinde_tn'] * precio_grano
        margen_ha = ingreso_ha - costo_sem_ha - costo_fijo
    else:
        col_ferti_matches = [c for c in joined.columns if any(k in c.lower() for k in ['part', 'urea', 'dosis', 'ferti'])]
        if col_ferti_matches:
            col_ferti = col_ferti_matches[0]
            joined['Urea_kg'] = pd.to_numeric(joined[col_ferti].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
        else:
            joined['Urea_kg'] = 0.0
        
        costo_sem_ha = costo_bolsa
        costo_urea_ha = (joined['Urea_kg'] / 1000) * costo_urea_tn
        ingreso_ha = joined['Rinde_tn'] * precio_grano
        margen_ha = ingreso_ha - costo_sem_ha - costo_urea_ha - costo_fijo

    joined['MargenUSD_ha'] = margen_ha.round(2)
    joined['IngresoUSD_ha'] = ingreso_ha.round(2)
    
    return joined.to_crs(epsg=4326)

if uploaded_file:
    with st.spinner("Procesando geometrías y calculando margen bruto por píxel..."):
        with tempfile.TemporaryDirectory() as tmpdir:
            if uploaded_file.name.endswith('.zip'):
                zip_path = os.path.join(tmpdir, "data.zip")
                with open(zip_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(tmpdir)
                shp_files = [f for f in os.listdir(tmpdir) if f.endswith('.shp')]
                gdf = gpd.read_file(os.path.join(tmpdir, shp_files[0]))
            else:
                kml_path = os.path.join(tmpdir, "data.kml")
                with open(kml_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                gdf = gpd.read_file(kml_path, driver='KML')

            gdf_resultado = procesar_mapa_economico(gdf)

    st.success(f"Mapa generado con éxito para {productor} - {establecimiento} ({lote_nombre})")

    c1, c2, c3 = st.columns(3)
    c1.metric("Margen Bruto Promedio", f"{gdf_resultado['MargenUSD_ha'].mean():.2f} USD/ha")
    c2.metric("Rendimiento Promedio", f"{gdf_resultado['Rinde_tn'].mean():.2f} tn/ha")
    c3.metric("Ingreso Promedio", f"{gdf_resultado['IngresoUSD_ha'].mean():.2f} USD/ha")

    st.subheader("🗺️ Visor Geográfico de Margen Bruto (10x10m)")
    
    centro_lat = gdf_resultado.geometry.centroid.y.mean()
    centro_lon = gdf_resultado.geometry.centroid.x.mean()
    
    m = folium.Map(location=[centro_lat, centro_lon], zoom_start=15, tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", attr="Google Hybrid")
    
    # -------------------------------------------------------------
    # CÁLCULO DE PALETA DINÁMICA (Rojo -> Amarillo -> Verde)
    # -------------------------------------------------------------
    v_min = float(gdf_resultado['MargenUSD_ha'].min())
    v_max = float(gdf_resultado['MargenUSD_ha'].max())
    rango = (v_max - v_min) if (v_max - v_min) > 0 else 1.0

    def get_color(val):
        pct = (val - v_min) / rango
        if pct < 0.5:
            # Rojo (231,76,60) a Amarillo (241,196,15)
            f = pct / 0.5
            r = 231 + int((241 - 231) * f)
            g = 76 + int((196 - 76) * f)
            b = 60 + int((15 - 60) * f)
        else:
            # Amarillo (241,196,15) a Verde (39,174,96)
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

    # Leyenda HTML flotante en la esquina inferior derecha del mapa
    leyenda_html = f'''
     <div style="
     position: fixed; 
     bottom: 30px; right: 30px; width: 220px; height: 90px; 
     background-color: rgba(255, 255, 255, 0.9);
     border:2px solid grey; z-index:9999; font-size:12px;
     padding: 8px; border-radius: 5px; font-family: sans-serif;">
     <b>Margen Bruto (USD/ha)</b><br>
     <div style="background: linear-gradient(to right, #e74c3c, #f1c40f, #27ae96); height: 15px; margin: 5px 0;"></div>
     <div style="display: flex; justify-content: space-between;">
        <span><b>Mín:</b> ${v_min:.0f}</span>
        <span><b>Máx:</b> ${v_max:.0f}</span>
     </div>
     </div>
     '''
    m.get_root().html.add_child(folium.Element(leyenda_html))

    st_folium(m, width=1100, height=550)

else:
    st.info("👈 Completa los parámetros en el panel izquierdo y sube un archivo (.zip o .kml) para generar el mapa.")