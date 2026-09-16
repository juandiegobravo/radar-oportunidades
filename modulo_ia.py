import os
import json
import time
import numpy as np
from openai import OpenAI, RateLimitError
from dotenv import load_dotenv

load_dotenv()

MODELO_EMBEDDINGS = "nvidia/nemotron-3-embed-1b:free"
TAM_LOTE_EMBEDDINGS = 100
PAUSA_ENTRE_LOTES = 1.5  # segundos entre peticiones, para no disparar el rate limit del modelo free
MAX_REINTENTOS_RATE_LIMIT = 5

REFERENCIA_EMBEDDINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'embeddings_referencia_brechas.json')

# Ejemplos reales (tomados de corridas anteriores) de lo que SÍ cuenta como
# oportunidad de negocio: marca/comercializadora, tarifa/producto energético
# o cluster temático de energía.
EJEMPLOS_BRECHA_BUENA = [
    # Marcas / comercializadoras
    "womwatt hogar net zero", "womwatt super precio", "womwatt energia net zero", "luzdostres",
    "solfy", "sotysolar", "ignis", "nordy", "powen", "solideo", "helioelec", "visalia",
    "about white", "butik", "e redes", "solelec", "eidf", "met",
    # Tarifas / productos (variedad de patrones marca+tarifa, luz y gas)
    "tarifa dh 2 0 td integra energia", "tarifa dh indexado trader pool eleia energia",
    "tarifa estable fija eco unielectrica", "tarifa fija anual", "tarifa 6 1",
    "tur gas tur 4", "catgas tarifa solar indexada dh catgas", "tarifa dh 2 0 td aracan energia",
    "tarifa dh 3 tramos energygo", "tarifa estable 24 horas nordy", "tarifa estable gas fija vivo energia",
    "tarifa indexada gas visalia", "solar 360", "solar 360 precio",
    # Clusters temáticos de energía
    "huerto solar", "autoconsumo remoto", "autoconsumo tipos", "cau autoconsumo",
    "inversor solar", "bateria de condensadores", "instaladores samara",
    "consultoria energetica barcelona", "consultoria energetica zaragoza",
    "gestion energetica administradores de fincas", "comunidades de vecinos",
    "administradores de fincas", "subvenciones comunidad valenciana",
    "barrios solares", "horas de sol", "impuesto sol", "inclinacion y orientacion",
    "normativa electrica comunidad de vecinos", "compensacion excentes",
    "coste comercialiacion", "precio medio ponderado", "cheapest energy deals",
    "power suppliers", "flex living",
    # Features/herramientas de marca de un competidor (sigue siendo marca/producto)
    "selectra score", "semaforo selectra", "semaforo selectra pool electrico",
]

# Ejemplos reales de ruido editorial (noticias, opinión, macro) que NO
# interesa aunque mencione energía de pasada.
EJEMPLOS_BRECHA_MALA = [
    "10 acciones para combatir el cambio climatico",
    "apagon hogares siguen sin estar preparados",
    "aviso cambios tarifas junio",
    "avisos cortes averias por sms",
    "cambia iva factura desde junio",
    "crisis oriente medio",
    "noticias canal whatsapp",
    "nuevo decreto energetico proteccion consumidor",
    "nutri score gastos hogar",
    "paquete medidas anticrisis",
    "posible acuerdo estrecho ormuz",
    "cnmc falsas deudas luz",
    "entender el recibo de la luz",
    "factura mes suministros basicos",
]

def _crear_cliente():
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or api_key == "tu_api_key_aqui":
        return None
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

def obtener_embeddings(textos, tam_lote=TAM_LOTE_EMBEDDINGS):
    """
    Genera un vector de embedding por cada texto de la lista, usando el
    modelo de embeddings de OpenRouter. Devuelve None si no hay API key o
    si falla la petición; devuelve [] si `textos` está vacío.
    """
    if not textos:
        return []

    client = _crear_cliente()
    if not client:
        print("Configura OPENROUTER_API_KEY en .env para generar embeddings.")
        return None

    vectores = []
    try:
        for i in range(0, len(textos), tam_lote):
            lote = textos[i:i + tam_lote]
            vectores.extend(_pedir_lote_embeddings(client, lote))
            if i + tam_lote < len(textos):
                time.sleep(PAUSA_ENTRE_LOTES)
        return vectores
    except Exception as e:
        print(f"Error con OpenRouter generando embeddings: {e}")
        return None

def _pedir_lote_embeddings(client, lote):
    espera = PAUSA_ENTRE_LOTES
    for intento in range(1, MAX_REINTENTOS_RATE_LIMIT + 1):
        try:
            respuesta = client.embeddings.create(model=MODELO_EMBEDDINGS, input=lote)
            return [item.embedding for item in respuesta.data]
        except RateLimitError as e:
            # El límite diario ("free-models-per-day") no se recupera en
            # segundos como uno por-minuto: reintentar con backoff solo
            # generaba una espera larga e inútil que parecía un cuelgue.
            if 'per-day' in str(e) or 'daily' in str(e).lower():
                print("Límite diario de OpenRouter agotado, no tiene sentido reintentar hasta el reset.")
                raise
            if intento == MAX_REINTENTOS_RATE_LIMIT:
                raise
            print(f"Rate limit de OpenRouter alcanzado, reintentando en {espera:.1f}s (intento {intento}/{MAX_REINTENTOS_RATE_LIMIT})...")
            time.sleep(espera)
            espera *= 2

def _embeddings_referencia_con_cache():
    """
    Embeddings de los ejemplos de referencia BUENA/MALA usados para
    clasificar relevancia de negocio. Se piden una única vez (son ~40
    textos fijos) y quedan cacheados en disco para siempre: a diferencia de
    un clasificador por chat, este paso NO vuelve a llamar a la IA en
    corridas futuras, así que su coste no depende de cuántas keywords traiga
    cada corrida.
    """
    if os.path.exists(REFERENCIA_EMBEDDINGS_FILE):
        try:
            with open(REFERENCIA_EMBEDDINGS_FILE, 'r') as f:
                cache = json.load(f)
            return cache.get('buena'), cache.get('mala')
        except json.JSONDecodeError:
            pass

    vectores_buena = obtener_embeddings(EJEMPLOS_BRECHA_BUENA)
    vectores_mala = obtener_embeddings(EJEMPLOS_BRECHA_MALA)
    if vectores_buena is None or vectores_mala is None:
        return None, None

    with open(REFERENCIA_EMBEDDINGS_FILE, 'w') as f:
        json.dump({'buena': vectores_buena, 'mala': vectores_mala}, f)
    return vectores_buena, vectores_mala

def relevancia_por_embeddings(vectores_candidatas):
    """
    Para cada embedding de candidata, decide si está más cerca (por
    similitud coseno) de los ejemplos de referencia BUENA (marca/
    comercializadora, tarifa/producto o cluster de energía) que de los de
    MALA (editorial genérico). Reutiliza embeddings que el caller ya pidió
    para el chequeo de similitud con Papernest, así que clasificar no cuesta
    peticiones extra a la IA (salvo, una única vez, embeber los ejemplos de
    referencia).

    Devuelve una lista de booleanos (uno por candidata, en el mismo orden).
    Si no hay ejemplos de referencia disponibles (sin API key o fallo de
    red), devuelve todo True para no perder brechas por no poder clasificar.
    """
    if not vectores_candidatas:
        return []

    vectores_buena, vectores_mala = _embeddings_referencia_con_cache()
    if vectores_buena is None or vectores_mala is None:
        return [True] * len(vectores_candidatas)

    matriz_candidatas = np.array(vectores_candidatas)
    normal_candidatas = matriz_candidatas / np.linalg.norm(matriz_candidatas, axis=1, keepdims=True)

    def _similitud_maxima(ejemplos_vectores):
        matriz = np.array(ejemplos_vectores)
        normal = matriz / np.linalg.norm(matriz, axis=1, keepdims=True)
        return (normal_candidatas @ normal.T).max(axis=1)

    sim_buena = _similitud_maxima(vectores_buena)
    sim_mala = _similitud_maxima(vectores_mala)

    return [bool(sb > sm) for sb, sm in zip(sim_buena, sim_mala)]

def gaps_por_similitud(candidatas, vectores_candidatas, vectores_propias, umbral):
    """
    Recibe keywords de un competidor que YA se filtraron (fuera de esta
    función) para eliminar cualquier coincidencia EXACTA con Papernest, junto
    con sus embeddings y los embeddings de todas las keywords propias.
    Compara cada candidata por similitud coseno contra TODAS las propias y
    se queda solo con las que no tienen ninguna suficientemente parecida
    (su similitud máxima está por debajo del umbral): esos son los gaps
    reales de contenido. Sin resumen ejecutivo ni keywords relacionadas.
    """
    if not candidatas:
        return []
    if not vectores_propias:
        # Papernest no tiene keywords con las que comparar: todo es gap.
        return list(candidatas)

    matriz_candidatas = np.array(vectores_candidatas)
    matriz_propias = np.array(vectores_propias)

    normal_candidatas = matriz_candidatas / np.linalg.norm(matriz_candidatas, axis=1, keepdims=True)
    normal_propias = matriz_propias / np.linalg.norm(matriz_propias, axis=1, keepdims=True)

    similitudes = normal_candidatas @ normal_propias.T
    similitud_maxima = similitudes.max(axis=1)

    return [candidatas[i] for i, sim in enumerate(similitud_maxima) if sim < umbral]
