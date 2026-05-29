import streamlit as st
import requests
import os
import rasterio
from rasterio.windows import from_bounds, Window
from geopy.geocoders import Nominatim
import math
import numpy as np
import io

# Lista de países en español y sus equivalentes en inglés para Nominatim
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
    "Portugal": "Portugal",
    "Francia": "France",
    "Italia": "Italy",
    "Alemania": "Germany",
    "Reino Unido": "United Kingdom",
    "Japón": "Japan",
    "China": "China",
    "Australia": "Australia",
    "Otros (Búsqueda Manual)": "manual"
}

# Constantes de URL y archivos
EGM2008_URL = "https://s3-eu-west-1.amazonaws.com/download.agisoft.com/gtg/us_nga_egm2008_1.tif"
DATA_DIR = "data"
EGM_FILE = os.path.join(DATA_DIR, "us_nga_egm2008_1.tif")

st.set_page_config(page_title="Descargador de Geoide", page_icon="🌍")

st.title("🌍 Descargador de Geoide EGM2008 de Alta Resolución (1')")
st.write("Esta herramienta recorta el modelo global de geoide EGM2008 (1 minuto de arco) para la zona del país seleccionado en el formato de tu elección.")

# Asegurar que existe la carpeta data
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Función para descargar el archivo global
@st.cache_resource(show_spinner=False)
def download_global_geoid():
    if not os.path.exists(EGM_FILE):
        st.info("El archivo global EGM2008 de 1' (aprox. 420 MB) no se encontró. Descargándolo (esto solo se hace una vez)...")
        response = requests.get(EGM2008_URL, stream=True)
        total_size_in_bytes = int(response.headers.get('content-length', 0))
        block_size = 1024 * 1024 # 1 Megabyte
        
        progress_bar = st.progress(0)
        downloaded = 0
        
        with open(EGM_FILE, 'wb') as file:
            for data in response.iter_content(block_size):
                downloaded += len(data)
                file.write(data)
                if total_size_in_bytes > 0:
                    progress = int(100 * downloaded / total_size_in_bytes)
                    progress_bar.progress(progress if progress <= 100 else 100)
        
        progress_bar.empty()
        st.success("Descarga del modelo global de 1' completada.")
    return True

# Función para obtener el bounding box de un país
def get_country_bbox(country_name):
    geolocator = Nominatim(user_agent="geoid_downloader_app_v2")
    try:
        location = geolocator.geocode({"country": country_name}, exactly_one=True)
        if location and location.raw.get('boundingbox'):
            bbox = location.raw['boundingbox']
            # Convertir a: [lon_min, lat_min, lon_max, lat_max]
            return (float(bbox[2]), float(bbox[0]), float(bbox[3]), float(bbox[1]))
    except Exception as e:
        st.error(f"Error al buscar coordenadas: {e}")
    return None

def crop_geoid(bbox, output_filename, format_type):
    lon_min, lat_min, lon_max, lat_max = bbox
    
    # Expandir el bounding box ligeramente para asegurar cobertura completa
    lon_min -= 0.5
    lat_min -= 0.5
    lon_max += 0.5
    lat_max += 0.5
    
    with rasterio.open(EGM_FILE) as src:
        # Calcular la ventana
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
            # Generar coordenadas X e Y para cada celda
            rows, cols = np.meshgrid(np.arange(height), np.arange(width), indexing='ij')
            xs, ys = rasterio.transform.xy(out_transform, rows, cols)
            
            # Aplanar los arreglos para guardarlos en formato columna (Lon, Lat, Altura)
            points = np.stack([np.array(xs).flatten(), np.array(ys).flatten(), data.flatten()], axis=1)
            
            s = io.StringIO()
            np.savetxt(s, points, fmt="%.6f,%.6f,%.4f", header="Longitud,Latitud,Altura_Geoide_m", comments="")
            with open(output_filename, "wb") as f:
                f.write(s.getvalue().encode('utf-8'))
        else:
            # Seleccionar el driver de GDAL
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

# Descargar modelo base en segundo plano si no existe
try:
    download_global_geoid()
except Exception as e:
    st.error(f"Error al descargar el geoide global: {e}")

# Formulario y Selección en la UI
paises_disponibles = list(PAISES.keys())
pais_seleccionado = st.selectbox("Selecciona un país:", paises_disponibles)

# Entrada manual si elige "Otros"
if pais_seleccionado == "Otros (Búsqueda Manual)":
    pais_busqueda = st.text_input("Ingresa el nombre del país en inglés (ej. Canada, Japan, Peru):")
else:
    pais_busqueda = PAISES[pais_seleccionado]

# Selección de formato de salida
formatos = [
    "GTX (VDatum)",
    "GeoTIFF (Raster Estándar)",
    "BYN (Formato Surveying)",
    "XYZ (Texto Plano/Excel)"
]
formato_seleccionado = st.selectbox("Selecciona el formato de descarga:", formatos)

# Mapear extensiones de archivo
extensiones = {
    "GTX (VDatum)": "gtx",
    "GeoTIFF (Raster Estándar)": "tif",
    "BYN (Formato Surveying)": "byn",
    "XYZ (Texto Plano/Excel)": "xyz"
}
ext = extensiones[formato_seleccionado]

if st.button("Generar y Descargar"):
    if pais_busqueda:
        nombre_pais_limpio = pais_seleccionado if pais_seleccionado != "Otros (Búsqueda Manual)" else pais_busqueda
        with st.spinner(f"Buscando límites geográficos para {nombre_pais_limpio}..."):
            bbox = get_country_bbox(pais_busqueda)
            
        if bbox:
            st.success(f"Coordenadas encontradas para {nombre_pais_limpio}: Longitud [{bbox[0]:.2f} a {bbox[2]:.2f}], Latitud [{bbox[1]:.2f} a {bbox[3]:.2f}]")
            
            nombre_archivo = f"{nombre_pais_limpio.replace(' ', '_').lower()}_geoid.{ext}"
            output_file = os.path.join(DATA_DIR, nombre_archivo)
            
            with st.spinner(f"Generando archivo en formato {formato_seleccionado}..."):
                try:
                    crop_geoid(bbox, output_file, formato_seleccionado)
                    st.success("¡Recorte y conversión exitosa!")
                    
                    with open(output_file, "rb") as file:
                        st.download_button(
                            label=f"⬇️ Descargar {nombre_archivo}",
                            data=file,
                            file_name=nombre_archivo,
                            mime="application/octet-stream"
                        )
                except Exception as e:
                    st.error(f"Error al procesar el archivo. El formato seleccionado podría no ser soportado por la versión de GDAL en el servidor. Detalles: {e}")
        else:
            st.error("No se pudo encontrar el país seleccionado. Intenta con búsqueda manual en inglés.")
    else:
        st.warning("Por favor ingresa un nombre para la búsqueda.")

# Créditos al pie de la página
st.markdown("---")
st.markdown(
    "<p style='text-align: center; color: #888888; font-weight: bold; margin-top: 50px;'>"
    "Diseñado para fines educativos por:<br>"
    "<span style='color: #4A90E2; font-size: 1.1em;'>Omar Cutimbo Ticona</span><br>"
    "TACNA - PERÚ"
    "</p>",
    unsafe_allow_html=True
)
