import streamlit as st
import requests
import os
import rasterio
from rasterio.windows import from_bounds, Window
from geopy.geocoders import Nominatim
import math

# Constantes
EGM2008_URL = "https://s3-eu-west-1.amazonaws.com/download.agisoft.com/gtg/us_nga_egm2008_1.tif"
DATA_DIR = "data"
EGM_FILE = os.path.join(DATA_DIR, "us_nga_egm2008_1.tif")

st.set_page_config(page_title="Descargador de Geoide GTX", page_icon="🌍")

st.title("🌍 Descargador de Geoide por País (Formato GTX) - 1'")
st.write("Esta herramienta descarga el modelo global EGM2008 de alta resolución (1 arc-minuto) y recorta la zona del país seleccionado en formato GTX.")

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
    geolocator = Nominatim(user_agent="geoid_downloader_app")
    try:
        # Añadir 'country' al query para mayor precisión
        location = geolocator.geocode({"country": country_name}, exactly_one=True)
        if location and location.raw.get('boundingbox'):
            # El boundingbox de Nominatim es [lat_min, lat_max, lon_min, lon_max]
            # Convertimos a formato [lon_min, lat_min, lon_max, lat_max] (left, bottom, right, top)
            bbox = location.raw['boundingbox']
            return (float(bbox[2]), float(bbox[0]), float(bbox[3]), float(bbox[1]))
    except Exception as e:
        st.error(f"Error buscando el país: {e}")
    return None

def crop_geoid(bbox, output_filename):
    lon_min, lat_min, lon_max, lat_max = bbox
    
    # Expandir el bounding box ligeramente para asegurar que cubra todo el país
    lon_min -= 0.5
    lat_min -= 0.5
    lon_max += 0.5
    lat_max += 0.5
    
    with rasterio.open(EGM_FILE) as src:
        # Calcular la ventana que corresponde al bounding box
        window_raw = from_bounds(lon_min, lat_min, lon_max, lat_max, src.transform)
        
        # Redondear a enteros para evitar problemas al leer y escribir
        col_off = math.floor(window_raw.col_off)
        row_off = math.floor(window_raw.row_off)
        width = math.ceil(window_raw.width)
        height = math.ceil(window_raw.height)
        
        # Limitar la ventana a los bordes del raster
        col_off = max(0, col_off)
        row_off = max(0, row_off)
        width = min(width, src.width - col_off)
        height = min(height, src.height - row_off)
        
        window = Window(col_off, row_off, width, height)
        
        # Leer los datos de esa ventana
        data = src.read(1, window=window)
        
        # Calcular el nuevo transform para la ventana recortada
        out_transform = src.window_transform(window)
        
        # Configurar los metadatos para el nuevo archivo
        out_meta = src.meta.copy()
        out_meta.update({
            "driver": "GTX",
            "height": height,
            "width": width,
            "transform": out_transform
        })
        
        # Guardar el archivo GTX recortado
        with rasterio.open(output_filename, "w", **out_meta) as dest:
            dest.write(data, 1)

# Interfaz de usuario principal
try:
    download_global_geoid()
except Exception as e:
    st.error(f"Error al descargar el geoide global: {e}")

country = st.text_input("Ingresa el nombre del país (ej. Colombia, Mexico, Spain):")

if st.button("Generar y Descargar"):
    if country:
        with st.spinner(f"Buscando coordenadas para {country}..."):
            bbox = get_country_bbox(country)
            
        if bbox:
            st.success(f"Coordenadas encontradas: Longitud [{bbox[0]:.2f} a {bbox[2]:.2f}], Latitud [{bbox[1]:.2f} a {bbox[3]:.2f}]")
            
            output_file = os.path.join(DATA_DIR, f"{country.replace(' ', '_').lower()}_geoid.gtx")
            
            with st.spinner("Recortando el modelo global (esto puede tomar unos segundos)..."):
                try:
                    crop_geoid(bbox, output_file)
                    st.success("¡Recorte exitoso!")
                    
                    with open(output_file, "rb") as file:
                        st.download_button(
                            label=f"⬇️ Descargar {country.replace(' ', '_').lower()}_geoid.gtx",
                            data=file,
                            file_name=f"{country.replace(' ', '_').lower()}_geoid.gtx",
                            mime="application/octet-stream"
                        )
                except Exception as e:
                    st.error(f"Ocurrió un error al procesar el archivo. Asegúrate de tener suficiente memoria RAM o de que el país sea válido. Detalles: {e}")
        else:
            st.error("No se pudo encontrar el país. Intenta con un nombre más común o en inglés.")
    else:
        st.warning("Por favor ingresa un nombre de país.")
