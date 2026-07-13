import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import re
import time

# --- CONFIGURACIÓN DE PARÁMETROS ---
URL_BASE = "https://www.gatotv.com/guia_tv/completa"
HORA_INICIO_DIFUSION = 8  # Iniciará a las 8:00 AM de tu día real actual

# OBTENER LA FECHA REAL DEL DÍA EN CURSO (Basado en tu computadora)
fecha_hoy = datetime.now().date()

# Calcular el desfase horario (Offset) exacto de tu propia máquina en tiempo real
# Ejemplo: Generará automáticamente "-0600", "-0500" o el que tenga tu sistema
offset_local = time.strftime("%z")
if not offset_local:
    offset_local = "-0600" # Respaldo por defecto en caso de error

# Calcular los límites del día actual (24 horas exactas)
inicio_bucle = datetime.combine(fecha_hoy, datetime.min.time()) + timedelta(hours=HORA_INICIO_DIFUSION)
fin_bucle = inicio_bucle + timedelta(hours=24)

print(f"Tu zona horaria local detectada es: {offset_local}")
print(f"Iniciando extracción desde: {inicio_bucle} hasta {fin_bucle}")

tv = ET.Element("tv")
canales_creados = set()
programas_por_canal = {}

momento_actual = inicio_bucle

# --- BUCLE DE EXTRACCIÓN POR INTERVALOS DE 2 HORAS ---
while momento_actual < fin_bucle:
    
    fecha_url = momento_actual.strftime("%Y-%m-%d")
    hora_url = momento_actual.strftime("%H-%M")
    
    URL = f"{URL_BASE}/{fecha_url}/{hora_url}"
    print(f"Consultando parrilla web: {URL}")
    
    try:
        html = requests.get(
            URL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=30
        ).text
    except Exception as e:
        print(f"Error de red, saltando intervalo: {e}")
        momento_actual += timedelta(hours=2)
        continue

    soup = BeautifulSoup(html, "html.parser")
    
    # Asegurar hora base
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

    try:
        hora_base_bloque = datetime.strptime(f"{fecha_url} {hora_tabla}", "%Y-%m-%d %H:%M")
    except ValueError:
        hora_base_bloque = datetime.combine(momento_actual.date(), datetime.strptime(hora_tabla, "%H:%M").time())
    
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
            # Sanitizar el nombre del canal antes de meterlo al XML
            canal_nombre_clean = canal_nombre.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")
            
            channel = ET.SubElement(tv, "channel", id=canal_id)
            display = ET.SubElement(channel, "display-name")
            display.text = canal_nombre_clean
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

            if inicio >= inicio_bucle and inicio < fin_bucle:
                identificador_programa = f"{inicio.strftime('%H%M')}_{titulo}"
                
                if identificador_programa not in programas_por_canal[canal_id]:
                    programas_por_canal[canal_id].append(identificador_programa)
                    
                    # SANITIZACIÓN IMPRESCINDIBLE PARA EVITAR ERRORES DE SINTAXIS XML (Como el error de m3u4u)
                    titulo_clean = titulo.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")
                    
                    # ASIGNACIÓN DE LA HORA CON TU OFFSET LOCAL DETECTADO AUTOMÁTICAMENTE
                    programa_xml = ET.SubElement(
                        tv,
                        "programme",
                        start=inicio.strftime(f"%Y%m%d%H%M%S {offset_local}"),
                        stop=fin.strftime(f"%Y%m%d%H%M%S {offset_local}"),
                        channel=canal_id
                    )
                    ET.SubElement(programa_xml, "title").text = titulo_clean

    momento_actual += timedelta(hours=2)
    time.sleep(1)

# --- GUARDAR MANDATORIAMENTE SOBREESCRIBIENDO EL ARCHIVO ---
tree = ET.ElementTree(tv)
tree.write("epg.xml", encoding="utf-8", xml_declaration=True)

print(f"\n--- ARCHIVO CREADO EXITOSAMENTE CON EL AÑO EN CURSO ---")
