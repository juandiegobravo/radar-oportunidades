import json
import os
import sys

import requests

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'volumen_ahrefs.json')
TIMEOUT_HTTP = 15  # segundos; sin esto una petición colgada bloquea el script indefinidamente


def main():
    if not os.path.exists(RUTA):
        print("No hay archivo de volumen pendiente (volumen_ahrefs.json no existe).")
        return

    with open(RUTA, 'r') as f:
        datos = json.load(f)

    if datos.get("enviado"):
        print("Este volumen ya se envió antes, nada que hacer.")
        return

    oportunidades = datos.get("oportunidades", [])
    if not oportunidades:
        print("volumen_ahrefs.json no tiene oportunidades, nada que enviar.")
        return

    lineas = []
    for o in oportunidades:
        volumen = o.get("volumen")
        volumen_texto = f"{volumen} búsquedas/mes (ES)" if volumen is not None else "sin dato de volumen"
        lineas.append(f"• *[{o['origen']}]* {o['titulo']} — {volumen_texto}")

    texto = "📊 *Volumen de búsqueda — Oportunidades de hoy*\n\n" + "\n".join(lineas)

    webhook_url = os.getenv("SLACK_WORKFLOW_WEBHOOK_URL")
    if not webhook_url or webhook_url == "tu_url_de_webhook_aqui":
        print("Configura SLACK_WORKFLOW_WEBHOOK_URL para enviar el volumen a Slack.")
        sys.exit(1)

    try:
        response = requests.post(webhook_url, json={"resumen": texto}, timeout=TIMEOUT_HTTP)
    except Exception as e:
        print(f"Error enviando petición a Slack: {e}")
        sys.exit(1)

    if response.status_code != 200:
        print(f"Error enviando a Slack (Status {response.status_code}): {response.text}")
        sys.exit(1)

    print(f"Volumen enviado a Slack ({len(oportunidades)} oportunidad(es)).")
    datos["enviado"] = True
    with open(RUTA, 'w') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
