import requests
from bs4 import BeautifulSoup

TIMEOUT_HTTP = 15  # segundos; sin esto una petición colgada bloquea el script indefinidamente

# 'pvpc' y 'peajes' ya son inequívocamente energéticas por sí solas.
# 'tarifas', 'miteco' y 'cnmc' son ambiguas (CNMC regula telecom también,
# tarifas puede ser de peajes de carretera, tasas administrativas, etc.), así
# que solo cuentan si además aparece una palabra de contexto energético en el
# mismo título/descripción.
PALABRAS_ENERGIA_ESPECIFICAS = ('pvpc', 'peajes')
PALABRAS_AMBIGUAS = ('tarifas', 'miteco', 'cnmc')
PALABRAS_CONTEXTO_ENERGIA = ('energ', 'eléctric', 'electric', 'luz', 'gas natural')

def _es_relevante_energia(texto):
    if any(p in texto for p in PALABRAS_ENERGIA_ESPECIFICAS):
        return True
    return any(p in texto for p in PALABRAS_AMBIGUAS) and any(p in texto for p in PALABRAS_CONTEXTO_ENERGIA)

def consultar_boe():
    # El BOE publica RSS diarios. Simplificamos consultando el RSS del día.
    url = "https://www.boe.es/rss/boe.php?c=todas"
    oportunidades = []

    try:
        response = requests.get(url, timeout=TIMEOUT_HTTP)
        soup = BeautifulSoup(response.content, 'xml')
        items = soup.find_all('item')

        for item in items:
            titulo = item.title.text.lower()
            descripcion = item.description.text.lower() if item.description else ""

            if _es_relevante_energia(f"{titulo} {descripcion}"):
                oportunidades.append({
                    'titulo': item.title.text,
                    'enlace': item.link.text
                })
        return oportunidades
    except Exception as e:
        print(f"Error accediendo al BOE: {e}")
        return []

def diagnosticar_boe():
    print("\n[DIAGNÓSTICO] Consultando BOE...")
    url = "https://www.boe.es/rss/boe.php?c=todas"
    try:
        response = requests.get(url, timeout=TIMEOUT_HTTP)
        soup = BeautifulSoup(response.content, 'xml')
        items = soup.find_all('item')
        
        encontrado = False
        for item in items:
            titulo = item.title.text
            descripcion = item.description.text if item.description else ""
            titulo_lower = titulo.lower()
            desc_lower = descripcion.lower()
            
            if 'transición ecológica' in titulo_lower or 'cnmc' in titulo_lower or 'transición ecológica' in desc_lower or 'cnmc' in desc_lower or 'energ' in titulo_lower or 'energ' in desc_lower:
                print(f"-> Último doc relacionado:\n   TÍTULO: {titulo}\n   RESUMEN: {descripcion}")
                encontrado = True
                break
                
        if not encontrado:
            print("-> No se encontraron documentos del MITECO/CNMC/Energía en el sumario actual.")
    except Exception as e:
        print(f"-> Error en diagnóstico BOE: {e}")
