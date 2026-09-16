import os
import json
import csv
import requests
from io import StringIO
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Anclado a la carpeta del script: si no, el archivo termina donde sea que
# estuviera el cwd al lanzar python3 main.py, no necesariamente aquí.
CENSO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'censo_local.json')
COL_EMPRESA = 'Nombre empresa'
COL_FECHA_ALTA = 'Fecha alta'
COL_ESTADO = 'Estado'
PALABRAS_BAJA = ('baja', 'inhabilit')
TIMEOUT_HTTP = 15  # segundos; sin esto una petición colgada bloquea el script indefinidamente
DIAS_VENTANA_ALTA_RECIENTE = 30  # la fuente (Sheet del censo) a veces se re-exporta/backfillea de golpe: si una empresa "nueva" en el snapshot local ya tiene Fecha alta más antigua que esto, no es un alta real reciente, es solo que ahora aparece en el Sheet

def parse_fecha(fecha_str):
    try:
        # Intentar parsear como DD/MM/YYYY
        return datetime.strptime(fecha_str.strip(), "%d/%m/%Y")
    except:
        return datetime.min

def analizar_datos_cnmc():
    url_csv = os.getenv("GOOGLE_SHEET_CENSO_CSV_URL")
    if not url_csv or url_csv == "tu_url_csv_aqui":
        print("Configura GOOGLE_SHEET_CENSO_CSV_URL en .env")
        return None

    try:
        response = requests.get(url_csv, timeout=TIMEOUT_HTTP)
        if response.status_code != 200:
            print(f"Error HTTP descargando el Sheet: {response.status_code}")
            return None

        f = StringIO(response.text)
        reader = csv.DictReader(f, delimiter=',')
        filas = list(reader)

        if not filas:
            return None

        columnas_faltantes = {COL_EMPRESA, COL_FECHA_ALTA, COL_ESTADO} - set(reader.fieldnames or [])
        if columnas_faltantes:
            print(f"El Sheet del censo CNMC no tiene las columnas esperadas: {columnas_faltantes}")
            return None

        empresas = {}
        ultima_empresa = ""
        ultima_fecha = ""
        max_fecha_dt = datetime.min

        # Lookup por nombre de columna en vez de índice: no depende de que
        # el Sheet mantenga el orden exacto de columnas.
        for fila in filas:
            empresa = (fila.get(COL_EMPRESA) or '').strip()
            fecha_str = (fila.get(COL_FECHA_ALTA) or '').strip()

            if not empresa:
                continue

            estado_str = (fila.get(COL_ESTADO) or '').strip().lower()
            es_baja = any(palabra in estado_str for palabra in PALABRAS_BAJA)

            empresas[empresa] = {
                "fecha": fecha_str,
                "baja": es_baja
            }

            fecha_dt = parse_fecha(fecha_str)
            if fecha_dt >= max_fecha_dt:
                max_fecha_dt = fecha_dt
                ultima_fecha = fecha_str
                ultima_empresa = empresa

        if empresas:
            return {
                "total": len(empresas),
                "ultima_empresa": ultima_empresa,
                "ultima_fecha": ultima_fecha,
                "ultima_fecha_iso": max_fecha_dt.isoformat(),
                "empresas": empresas
            }
        return None
    except Exception as e:
        print(f"Error analizando el CSV del Google Sheet: {e}")
        return None

def _guardar_censo(datos):
    with open(CENSO_FILE, 'w') as f:
        json.dump(datos, f)

def detectar_altas_bajas_cnmc():
    datos_actuales = analizar_datos_cnmc()
    if not datos_actuales:
        return []

    if os.path.exists(CENSO_FILE):
        try:
            with open(CENSO_FILE, 'r') as f:
                datos_guardados = json.load(f)
        except json.JSONDecodeError:
            datos_guardados = {}
    else:
        datos_guardados = {}

    # Primera ejecución (o censo local en formato antiguo sin detalle por
    # empresa): se guarda como línea base sin generar alertas, ya que no
    # hay nada previo con lo que comparar altas/bajas reales.
    if "empresas" not in datos_guardados:
        _guardar_censo(datos_actuales)
        return []

    empresas_actuales = datos_actuales["empresas"]
    empresas_guardadas = datos_guardados["empresas"]

    alertas = []
    descartadas_por_antiguedad = 0

    for nombre, info in empresas_actuales.items():
        guardada = empresas_guardadas.get(nombre)
        if guardada is None:
            fecha_dt = parse_fecha(info["fecha"])
            dias_desde_alta = (datetime.now() - fecha_dt).days if fecha_dt != datetime.min else None
            if dias_desde_alta is not None and dias_desde_alta > DIAS_VENTANA_ALTA_RECIENTE:
                descartadas_por_antiguedad += 1
                continue
            alertas.append({
                "titulo": f"Nueva comercializadora: {nombre}",
                "detalle": f"Alta detectada en el censo CNMC con fecha {info['fecha']}."
            })
        elif info["baja"] and not guardada.get("baja"):
            alertas.append({
                "titulo": f"Baja de comercializadora: {nombre}",
                "detalle": "La comercializadora ha cambiado su estado a inhabilitada/baja en el censo CNMC."
            })

    for nombre in empresas_guardadas:
        if nombre not in empresas_actuales:
            alertas.append({
                "titulo": f"Baja de comercializadora: {nombre}",
                "detalle": "La comercializadora ya no aparece en el censo CNMC."
            })

    if descartadas_por_antiguedad:
        print(f"CNMC: {descartadas_por_antiguedad} empresa(s) nueva(s) en el Sheet descartada(s) por tener Fecha alta de más de {DIAS_VENTANA_ALTA_RECIENTE} días (probable re-exportación de la fuente, no alta real).")

    _guardar_censo(datos_actuales)
    return alertas

def diagnosticar_cnmc():
    print("\n[DIAGNÓSTICO] Consultando CNMC desde Google Sheets...")
    datos = analizar_datos_cnmc()
    if datos:
        print(f"-> Comercializadoras analizadas: {datos['total']}")
        print(f"-> Última empresa detectada: {datos['ultima_empresa']} (Fecha: {datos['ultima_fecha']})")
    else:
        print("-> No se pudo obtener o procesar el censo desde Google Sheets.")
