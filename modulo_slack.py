import os
import requests
from dotenv import load_dotenv

load_dotenv()

TIMEOUT_HTTP = 15  # segundos; sin esto una petición colgada bloquea el script indefinidamente
MAX_ITEMS_EN_MENSAJE = 50  # Slack corta/renderiza mal mensajes muy largos

def enviar_resumen_slack(oportunidades):
    """
    Envía un único mensaje resumen a Slack con todas las oportunidades de la
    corrida (en vez de un mensaje por oportunidad, para no saturar el canal).
    `oportunidades` es una lista de dicts con "origen" y "titulo".
    """
    webhook_url = os.getenv("SLACK_WORKFLOW_WEBHOOK_URL")
    if not webhook_url or webhook_url == "tu_url_de_webhook_aqui":
        print("Configura SLACK_WORKFLOW_WEBHOOK_URL en .env para enviar el resumen a Slack.")
        return

    total = len(oportunidades)

    if total == 0:
        # Mensaje explícito de "sin novedades": así se sabe que el radar
        # corrió (y no que se quedó colgado o falló en silencio).
        texto = "📡 *Radar de Contenido Eléctrico* — hoy no se han detectado nuevas oportunidades."
    else:
        visibles = oportunidades[:MAX_ITEMS_EN_MENSAJE]
        lineas = [f"• *[{o['origen']}]* {o['titulo']}" for o in visibles]
        if total > MAX_ITEMS_EN_MENSAJE:
            lineas.append(f"_...y {total - MAX_ITEMS_EN_MENSAJE} más (ver Sheet1 para el listado completo)._")

        texto = f"📡 *Radar de Contenido Eléctrico* — {total} oportunidad(es) nueva(s)\n\n" + "\n".join(lineas)

    # El webhook de un Workflow de Slack (a diferencia de un Incoming
    # Webhook clásico) no acepta {"text": ...}: espera un JSON con las
    # variables que se hayan definido en el paso "Webhook" del workflow.
    # Aquí usamos una única variable de texto llamada "resumen" — debe
    # llamarse exactamente igual en el workflow (ver instrucciones).
    payload = {"resumen": texto}

    try:
        response = requests.post(webhook_url, json=payload, timeout=TIMEOUT_HTTP)
        if response.status_code == 200:
            print(f"Resumen enviado a Slack ({total} oportunidad(es)).")
        else:
            print(f"Error enviando a Slack (Status {response.status_code}): {response.text}")
    except Exception as e:
        print(f"Error enviando petición a Slack: {e}")
