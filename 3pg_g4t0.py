import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import re
import time

# --- CONFIGURACIÓN DE PARÁMETROS ---
URL_BASE = "https://www.gatotv.com/guia_tv/completa"
HORA_INICIO_DIFUSION = 8  # Indica que iniciará a las 8:00 AM

# Calcular los límites del día (24 horas exactas)
fecha_hoy = datetime.now().date()
inicio_bucle = datetime.combine(fecha_hoy, datetime.min.time()) + timedelta(hours=HORA_INICIO_DIFUSION)
fin_bucle = inicio_bucle + timedelta(hours=24)

print(f"Iniciando extracción desde: {inicio_bucle} hasta {fin_bucle}")

tv = ET.Element("tv")
canales_creados = set()
programas_por_canal = {} # Control de duplicados por canal

momento_actual = inicio_bucle

# --- BUCLE DE EXTRACCIÓN POR INTERVALOS DE 2 HORAS ---
while momento_actual < fin_bucle:
    
    # GatoTV requiere el formato YYYY-MM-DD y HH-MM en la URL
    fecha_url = momento_actual.strftime("%Y-%m-%d")
    hora_url = momento_actual.strftime("%H-%M")
    
    # CONSTRUCCIÓN DE LA URL DINÁMICA USANDO LA CONSTANTE BASE
    URL = f"{URL_BASE}/{fecha_url}/{hora_url}"
    print(f"Descargando bloque: {fecha_url} a las {momento_actual.strftime('%H:%M')}...")
    print(f"Enlace consultado: {URL}")
    
    try:
        html = requests.get(
            URL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=30
        ).text
    except Exception as e:
        print(f"Error al descargar bloque, saltando al siguiente intervalo: {e}")
        momento_actual += timedelta(hours=2)
        continue

    soup = BeautifulSoup(html, "html.parser")
    
    # Leer la hora real devuelta por la tabla de la página
    time_selectors = soup.select(".div_EPG_Time, .epg_time_cell, td.tbl_EPG_times")
    hora_tabla = momento_actual.strftime("%H:%M")
    
    for cell in time_selectors:
        texto_hora = cell.get_text(strip=True)
        match = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)?", texto_hora, re.IGNORECASE)
        if match:
            hora = int(match.group(1))
            minutos = match.group(2)
            periodo = match.group(3)
            if periodo:
                periodo = periodo.upper()
                if periodo == "PM" and hora < 12: hora += 12
                elif periodo == "AM" and hora == 12: hora = 0
            hora_tabla = f"{hora:02d}:{minutos}"
            break

    # Definir el punto de inicio de tiempo exacto para este segmento parseado
    hora_base_bloque = datetime.strptime(f"{fecha_url} {hora_tabla}", "%Y-%m-%d %H:%M")
    
    filas = soup.select("tr.tbl_EPG_row, tr.tbl_EPG_rowAlternate")
    
    for fila in filas:
        celdas = fila.find_all("td")
        if len(celdas) < 2:
            continue

        canal_td = celdas[0]
        enlaces = canal_td.find_all("a")

        if len(enlaces) >= 2:
            canal_nombre = enlaces[-1].get_text(strip=True)
        elif len(enlaces) == 1:
            canal_nombre = enlaces[0].get_text(strip=True)
        else:
            continue

        canal_id = re.sub(r"[^a-z0-9]+", "_", canal_nombre.lower()).strip("_")

        if canal_id not in canales_creados:
            channel = ET.SubElement(tv, "channel", id=canal_id)
            display = ET.SubElement(channel, "display-name")
            display.text = canal_nombre
            canales_creados.add(canal_id)
            programas_por_canal[canal_id] = []

        momento_programa = hora_base_bloque

        for programa_td in celdas[1:]:
            try:
                duracion = int(programa_td.get("colspan", "0"))
            except:
                duracion = 0

            if duracion <= 0:
                continue

            titulo = programa_td.get_text(" ", strip=True)
            titulo = " ".join(titulo.split())

            if not titulo:
                momento_programa += timedelta(minutes=duracion)
                continue

            inicio = momento_programa
            fin = momento_programa + timedelta(minutes=duracion)
            momento_programa = fin 

            # Filtrar que el programa pertenezca estrictamente al rango de 24 horas solicitado
            if inicio >= inicio_bucle and inicio < fin_bucle:
                identificador_programa = f"{inicio.strftime('%H%M')}_{titulo}"
                
                if identificador_programa not in programas_por_canal[canal_id]:
                    programas_por_canal[canal_id].append(identificador_programa)
                    
                    programa_xml = ET.SubElement(
                        tv,
                        "programme",
                        start=inicio.strftime("%Y%m%d%H%M%S -0600"),
                        stop=fin.strftime("%Y%m%d%H%M%S -0600"),
                        channel=canal_id
                    )
                    ET.SubElement(programa_xml, "title").text = titulo

    # Avanzar 2 horas para procesar la siguiente sección de la parrilla
    momento_actual += timedelta(hours=2)
    time.sleep(1) # Espera obligatoria para evitar sobrecargar el servidor

# --- GUARDAR XML FINAL ---
tree = ET.ElementTree(tv)
tree.write("epg.xml", encoding="utf-8", xml_declaration=True)

print("\n--- PROCESO FINALIZADO CON ÉXITO ---")
print("Canales únicos procesados:", len(canales_creados))
print("Archivo maestro generado listo para usar: epg.xml")
