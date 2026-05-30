import streamlit as st
import requests
import os
import rasterio
from rasterio.windows import from_bounds, Window
from geopy.geocoders import Nominatim
import math
import numpy as np
import io
import folium
from streamlit_folium import st_folium

# Mapeo de países comunes en español a inglés
PAISES = {
    "Perú": "Peru",
    "Colombia": "Colombia",
    "México": "Mexico",
    "España": "Spain",
    "Argentina": "Argentina",
    "Chile": "Chile",
    "Ecuador": "Ecuador",
    "Bolivia": "Bolivia",
    "Venezuela": "Venezuela",
    "Uruguay": "Uruguay",
    "Paraguay": "Paraguay",
    "Costa Rica": "Costa Rica",
    "Panamá": "Panama",
    "Guatemala": "Guatemala",
    "Honduras": "Honduras",
    "El Salvador": "El Salvador",
    "Nicaragua": "Nicaragua",
    "República Dominicana": "Dominican Republic",
    "Cuba": "Cuba",
    "Puerto Rico": "Puerto Rico",
    "Estados Unidos": "United States",
    "Canadá": "Canada",
    "Brasil": "Brazil",
    "Sudamérica": "South America",
    "Centroamérica": "Central America",
    "Norteamérica": "North America",
    "Europa": "Europe",
    "Búsqueda Libre (Cualquier lugar, ciudad o región)": "manual"
}

# Resoluciones
RESOLUCIONES = {
    "1' (Alta precisión - 1 Minuto de arco)": {
        "url": "https://s3-eu-west-1.amazonaws.com/download.agisoft.com/gtg/us_nga_egm2008_1.tif",
        "file": "us_nga_egm2008_1.tif"
    },
    "2.5' (Mediana precisión - 2.5 Minutos de arco)": {
        "url": "https://s3-eu-west-1.amazonaws.com/download.agisoft.com/gtg/us_nga_egm2008_25.tif",
        "file": "us_nga_egm2008_25.tif"
    }
}

DATA_DIR = "data"

st.set_page_config(page_title="DESCARGA TU GEOIDE EGM2008", page_icon="🌍", layout="wide")

st.title("DESCARGA TU GEOIDE EGM2008")
st.write("Herramienta para recortar y descargar el modelo de geoide EGM2008 para cualquier país, ciudad, continente o zona personalizada.")

# Asegurar que existe la carpeta data
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Estado del sistema (Permanente y discreto)
st.success("🟢 Aplicativo activo y funcional")

# Función para descargar el archivo global de forma silenciosa
def ensure_base_geoid(res_config):
    filepath = os.path.join(DATA_DIR, res_config["file"])
    if not os.path.exists(filepath):
        with st.spinner("Descargando base de datos del geoide global por primera vez. Por favor, espere..."):
            response = requests.get(res_config["url"], stream=True)
            with open(filepath, 'wb') as file:
                for data in response.iter_content(1024 * 1024):
                    file.write(data)
    return filepath

# Función para obtener el bounding box de cualquier consulta
def get_location_bbox(query):
    geolocator = Nominatim(user_agent="geoid_downloader_app_v3")
    try:
        location = geolocator.geocode(query, exactly_one=True)
        if location and location.raw.get('boundingbox'):
            bbox = location.raw['boundingbox']
            # Convertir a: [lon_min, lat_min, lon_max, lat_max]
            return (float(bbox[2]), float(bbox[0]), float(bbox[3]), float(bbox[1])), location.address
    except Exception as e:
        st.error(f"Error al buscar coordenadas: {e}")
    return None, None

def crop_geoid(base_file, bbox, output_filename, format_type):
    lon_min, lat_min, lon_max, lat_max = bbox
    
    # Margen extra
    lon_min -= 0.1
    lat_min -= 0.1
    lon_max += 0.1
    lat_max += 0.1
    
    with rasterio.open(base_file) as src:
        window_raw = from_bounds(lon_min, lat_min, lon_max, lat_max, src.transform)
        
        col_off = max(0, math.floor(window_raw.col_off))
        row_off = max(0, math.floor(window_raw.row_off))
        width = min(math.ceil(window_raw.width), src.width - col_off)
        height = min(math.ceil(window_raw.height), src.height - row_off)
        
        window = Window(col_off, row_off, width, height)
        
        # Leer datos
        data = src.read(1, window=window)
        out_transform = src.window_transform(window)
        
        if format_type == "XYZ (Texto Plano/Excel)":
            rows, cols = np.meshgrid(np.arange(height), np.arange(width), indexing='ij')
            xs, ys = rasterio.transform.xy(out_transform, rows, cols)
            
            points = np.stack([np.array(xs).flatten(), np.array(ys).flatten(), data.flatten()], axis=1)
            
            s = io.StringIO()
            np.savetxt(s, points, fmt="%.6f,%.6f,%.4f", header="Longitud,Latitud,Altura_Geoide_m", comments="")
            with open(output_filename, "wb") as f:
                f.write(s.getvalue().encode('utf-8'))
        else:
            driver_name = "GTX"
            if format_type == "GeoTIFF (Raster Estándar)":
                driver_name = "GTiff"
            elif format_type == "BYN (Formato Surveying)":
                driver_name = "BYN"
            
            out_meta = src.meta.copy()
            out_meta.update({
                "driver": driver_name,
                "height": height,
                "width": width,
                "transform": out_transform
            })
            
            with rasterio.open(output_filename, "w", **out_meta) as dest:
                dest.write(data, 1)

# --- DISEÑO DE COLUMNAS DE LA APLICACIÓN ---
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Configuración de Descarga")
    
    # 1. Selección de Resolución
    res_key = st.radio("Selecciona la resolución del geoide:", list(RESOLUCIONES.keys()))
    res_config = RESOLUCIONES[res_key]
    
    # Asegurar el archivo base
    base_file = ensure_base_geoid(res_config)
    
    # 2. Selección de Zona / Localidad
    paises_disponibles = list(PAISES.keys())
    pais_seleccionado = st.selectbox("Selecciona un país, región o continente:", paises_disponibles)
    
    if pais_seleccionado == "Búsqueda Libre (Cualquier lugar, ciudad o región)":
        consulta_busqueda = st.text_input("Ingresa el lugar que buscas (ej: Tacna, Lima, Buenos Aires, Sudamérica):", value="Tacna, Peru")
    else:
        consulta_busqueda = pais_seleccionado
    
    # Obtener coordenadas del área seleccionada
    bbox, direccion_completa = get_location_bbox(consulta_busqueda)
    
    # 3. Selección de formato de salida
    formatos = [
        "GTX (VDatum)",
        "GeoTIFF (Raster Estándar)",
        "BYN (Formato Surveying)",
        "XYZ (Texto Plano/Excel)"
    ]
    formato_seleccionado = st.selectbox("Selecciona el formato de archivo de salida:", formatos)
    
    extensiones = {
        "GTX (VDatum)": "gtx",
        "GeoTIFF (Raster Estándar)": "tif",
        "BYN (Formato Surveying)": "byn",
        "XYZ (Texto Plano/Excel)": "xyz"
    }
    ext = extensiones[formato_seleccionado]

with col2:
    st.subheader("Visualización del Área de Recorte")
    if bbox:
        lon_min, lat_min, lon_max, lat_max = bbox
        centro_lat = (lat_min + lat_max) / 2
        centro_lon = (lon_min + lon_max) / 2
        
        st.write(f"📍 **Ubicación encontrada:** {direccion_completa}")
        st.write(f"📐 **Límites:** Latitud [{lat_min:.4f} a {lat_max:.4f}] | Longitud [{lon_min:.4f} a {lon_max:.4f}]")
        
        # Crear mapa folium interactivo
        m = folium.Map(location=[centro_lat, centro_lon], zoom_start=4)
        
        # Dibujar rectángulo del área de recorte
        folium.Rectangle(
            bounds=[[lat_min, lon_min], [lat_max, lon_max]],
            color="#FF0000",
            fill=True,
            fill_color="#FF0000",
            fill_opacity=0.2,
            popup="Zona de Recorte"
        ).add_to(m)
        
        # Ajustar el mapa al rectángulo
        m.fit_bounds([[lat_min, lon_min], [lat_max, lon_max]])
        
        # Renderizar mapa en streamlit
        st_folium(m, width="100%", height=350, returned_objects=[])
    else:
        st.warning("Escribe una ubicación válida para verla en el mapa.")

# --- BOTÓN DE PROCESAMIENTO Y DESCARGA ---
st.markdown("---")
if bbox:
    nombre_archivo = f"{consulta_busqueda.replace(' ', '_').replace(',', '').lower()}_geoid.{ext}"
    output_path = os.path.join(DATA_DIR, nombre_archivo)
    
    if st.button("Generar y Descargar Archivo"):
        with st.spinner("Procesando y recortando geoide..."):
            try:
                crop_geoid(base_file, bbox, output_path, formato_seleccionado)
                st.success("¡Procesamiento exitoso!")
                
                with open(output_path, "rb") as file:
                    st.download_button(
                        label=f"⬇️ Descargar {nombre_archivo}",
                        data=file,
                        file_name=nombre_archivo,
                        mime="application/octet-stream"
                    )
            except Exception as e:
                st.error(f"Error al generar el archivo. El formato seleccionado podría no ser compatible con el servidor. Detalles: {e}")

# Créditos al pie de la página
st.markdown("---")
st.markdown(
    "<p style='text-align: center; color: #888888; font-weight: bold; margin-top: 30px;'>"
    "Diseñado para fines educativos por:<br>"
    "<span style='color: #4A90E2; font-size: 1.1em;'>Omar Cutimbo Ticona</span><br>"
    "TACNA - PERÚ"
    "</p>",
    unsafe_allow_html=True
)
