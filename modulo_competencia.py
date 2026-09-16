import os
import csv
import json
from io import StringIO
import requests
from dotenv import load_dotenv
from modulo_ia import obtener_embeddings, gaps_por_similitud, relevancia_por_embeddings
from progreso import iniciar_cronometro

load_dotenv()

FUENTES_COMPETENCIA = [
    ("Rastreator", "GOOGLE_SHEET_RASTREATOR_CSV_URL"),
    ("Selectra", "GOOGLE_SHEET_SELECTRA_CSV_URL"),
    ("Roams", "GOOGLE_SHEET_ROAMS_CSV_URL"),
]
ENV_PAPERNEST = "GOOGLE_SHEET_PAPERNEST_CSV_URL"
# Anclados a la carpeta del script: si no, terminan donde sea que estuviera
# el cwd al lanzar python3 main.py, no necesariamente aquí.
_DIR = os.path.dirname(os.path.abspath(__file__))
OPORTUNIDADES_FILE = os.path.join(_DIR, 'oportunidades_local.json')
EMBEDDINGS_PAPERNEST_FILE = os.path.join(_DIR, 'embeddings_papernest.json')
EMBEDDINGS_COMPETENCIA_FILE = os.path.join(_DIR, 'embeddings_competencia.json')
UMBRAL_SIMILITUD = 0.50  # cosine similarity; súbelo/bájalo si hay falsos positivos/negativos
TIMEOUT_HTTP = 15  # segundos; sin esto una petición colgada bloquea el script indefinidamente

def leer_urls_sheet(env_var):
    url_csv = os.getenv(env_var)
    if not url_csv or url_csv == "tu_url_csv_aqui":
        print(f"Configura {env_var} en .env")
        return []

    try:
        response = requests.get(url_csv, timeout=TIMEOUT_HTTP)
        if response.status_code != 200:
            print(f"Error HTTP descargando {env_var}: {response.status_code}")
            return []

        f = StringIO(response.text)
        reader = csv.reader(f, delimiter=',')
        filas = list(reader)

        entradas = []
        # Columna A = URL de la página, Columna B = keywords de esa página.
        for fila in filas[1:]:
            if not fila or not fila[0].strip():
                continue
            url = fila[0].strip()
            keywords = fila[1].strip() if len(fila) > 1 else ""
            entradas.append({"url": url, "keywords": keywords})
        return entradas
    except Exception as e:
        print(f"Error leyendo {env_var}: {e}")
        return []

def _normalizar_keyword(kw):
    return kw.strip().lower()

def _es_contenido_empresas(keyword):
    # Papernest no atiende negocios/B2B, así que ninguna oportunidad sobre
    # empresas es accionable aunque sea marca/tarifa/cluster válido.
    return "empresa" in keyword

def _set_keywords(entradas):
    keywords = set()
    for e in entradas:
        if not e["keywords"]:
            continue
        for kw in e["keywords"].split(','):
            kw_norm = _normalizar_keyword(kw)
            if kw_norm:
                keywords.add(kw_norm)
    return keywords

def _cargar_oportunidades():
    if os.path.exists(OPORTUNIDADES_FILE):
        try:
            with open(OPORTUNIDADES_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def _guardar_oportunidades(datos):
    with open(OPORTUNIDADES_FILE, 'w') as f:
        json.dump(datos, f)

def _cargar_json(path):
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def _guardar_json(path, datos):
    with open(path, 'w') as f:
        json.dump(datos, f)

def _embeddings_con_cache(cache_file, keywords_lista, etiqueta):
    """
    Las keywords ya vistas en corridas anteriores no cambian de significado,
    así que se guardan en disco (por texto, no por origen) y solo se piden a
    la IA las que sean nuevas. Esto evita repetir peticiones de embeddings en
    cada ejecución para keywords que ya se analizaron antes.
    """
    cache = _cargar_json(cache_file)
    faltantes = [kw for kw in keywords_lista if kw not in cache]

    if faltantes:
        print(f"{len(keywords_lista) - len(faltantes)} keyword(s) de {etiqueta} ya en caché, generando embeddings de {len(faltantes)} nueva(s)...")
        nuevos_vectores = obtener_embeddings(faltantes)
        if nuevos_vectores is None:
            return None
        for kw, vector in zip(faltantes, nuevos_vectores):
            cache[kw] = vector
        _guardar_json(cache_file, cache)
    else:
        print(f"Las {len(keywords_lista)} keywords de {etiqueta} ya estaban en caché, sin peticiones nuevas.")

    return [cache[kw] for kw in keywords_lista]

def _embeddings_papernest_con_cache(keywords_lista):
    return _embeddings_con_cache(EMBEDDINGS_PAPERNEST_FILE, keywords_lista, "Papernest")

def detectar_content_gap(progreso_callback=None):
    entradas_papernest = leer_urls_sheet(ENV_PAPERNEST)
    keywords_propias_set = _set_keywords(entradas_papernest)
    keywords_propias_lista = sorted(keywords_propias_set)
    oportunidades_guardadas = _cargar_oportunidades()

    detener_cronometro = iniciar_cronometro(f"Embeddings de {len(keywords_propias_lista)} keywords propias de Papernest")
    vectores_propias = _embeddings_papernest_con_cache(keywords_propias_lista)
    detener_cronometro()

    gaps = []

    for origen, env_var in FUENTES_COMPETENCIA:
        entradas_competidor = leer_urls_sheet(env_var)
        keywords_competencia = _set_keywords(entradas_competidor)
        ya_reportados = set(oportunidades_guardadas.get(origen, []))

        if not keywords_competencia:
            print(f"[{origen}] Sin keywords para analizar.")
            if progreso_callback:
                progreso_callback(origen)
            continue

        # Descarta primero, sin IA, cualquier keyword que ya exista tal cual
        # en Papernest: eso nunca debe marcarse como oportunidad.
        candidatas_exactas = sorted(keywords_competencia - keywords_propias_set)
        antes_filtro_empresas = len(candidatas_exactas)
        candidatas_exactas = [kw for kw in candidatas_exactas if not _es_contenido_empresas(kw)]
        descartadas_empresas = antes_filtro_empresas - len(candidatas_exactas)
        print(f"[{origen}] {len(keywords_competencia)} keywords totales, {antes_filtro_empresas} sin coincidencia exacta en Papernest"
              + (f", {descartadas_empresas} descartada(s) por ser de empresas/B2B" if descartadas_empresas else "") + ".")

        if not candidatas_exactas or vectores_propias is None:
            print(f"[{origen}] 0 brecha(s) de contenido.")
            if progreso_callback:
                progreso_callback(origen)
            continue

        detener_cronometro = iniciar_cronometro(f"[{origen}] Embeddings de {len(candidatas_exactas)} keywords candidatas")
        vectores_exactas = _embeddings_con_cache(EMBEDDINGS_COMPETENCIA_FILE, candidatas_exactas, origen)
        detener_cronometro()

        if vectores_exactas is None:
            print(f"[{origen}] 0 brecha(s) de contenido (sin embeddings disponibles).")
            if progreso_callback:
                progreso_callback(origen)
            continue

        # Filtra ruido editorial (noticias, opinión, macro) y se queda solo
        # con marcas/comercializadoras, tarifas/productos o clusters de
        # energía: eso es lo que cuenta como oportunidad de negocio real.
        # Reutiliza los embeddings ya calculados arriba (no pide nada nuevo
        # a la IA), así el coste no crece con el volumen de keywords.
        mascara_relevancia = relevancia_por_embeddings(vectores_exactas)
        candidatas = [kw for kw, ok in zip(candidatas_exactas, mascara_relevancia) if ok]
        vectores_candidatas = [v for v, ok in zip(vectores_exactas, mascara_relevancia) if ok]
        print(f"[{origen}] {len(candidatas)} de {len(candidatas_exactas)} keywords son relevantes de negocio (marca/tarifa/cluster) tras filtrar editorial.")

        if not candidatas:
            print(f"[{origen}] 0 brecha(s) de contenido.")
            if progreso_callback:
                progreso_callback(origen)
            continue

        temas_gap = gaps_por_similitud(candidatas, vectores_candidatas, vectores_propias, UMBRAL_SIMILITUD)

        # Ya no se reportan gaps que ya se enviaron a Sheet1 en una ejecución
        # anterior, para no recomendar siempre lo mismo.
        temas_nuevos = [t for t in temas_gap if _normalizar_keyword(t) not in ya_reportados]
        print(f"[{origen}] {len(temas_gap)} brecha(s) detectada(s) por similitud, {len(temas_nuevos)} nueva(s) sin reportar antes.")

        for tema in temas_nuevos:
            gaps.append({
                "origen": origen,
                "titulo": tema
            })

        oportunidades_guardadas[origen] = sorted(ya_reportados | {_normalizar_keyword(t) for t in temas_gap})

        if progreso_callback:
            progreso_callback(origen)

    _guardar_oportunidades(oportunidades_guardadas)
    return gaps
