import os
import requests
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

TIMEOUT_HTTP = 15  # segundos; sin esto una petición colgada bloquea el script indefinidamente

def guardar_en_sheets(origen, datos_ia):
    webhook_url = os.getenv("GOOGLE_SHEETS_WEBHOOK_URL")
    if not webhook_url or webhook_url == "tu_url_de_webhook_aqui":
        print("Configura GOOGLE_SHEETS_WEBHOOK_URL en .env")
        return

    try:
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "fecha": fecha,
            "origen": origen,
            "titulo_sugerido": datos_ia.get("Titulo Sugerido", ""),
            "idea_principal": datos_ia.get("Idea Principal", ""),
            "palabras_clave": datos_ia.get("Palabras Clave", "")
        }
        
        response = requests.post(webhook_url, json=payload, timeout=TIMEOUT_HTTP)
        
        if response.status_code == 200 or response.status_code == 302:
            print(f"Oportunidad guardada vía Webhook: {datos_ia.get('Titulo Sugerido', '')}")
        else:
            print(f"Error guardando en Webhook (Status {response.status_code})")
    except Exception as e:
        print(f"Error enviando petición al Webhook: {e}")
