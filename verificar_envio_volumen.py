import json
import os
import sys

import requests

_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_OPORTUNIDADES = os.path.join(_DIR, 'ultimas_oportunidades_nuevas.json')
RUTA_VOLUMEN = os.path.join(_DIR, 'volumen_ahrefs.json')
TIMEOUT_HTTP = 15  # segundos; sin esto una petición colgada bloquea el script indefinidamente


def _misma_fecha(a, b):
    # Compara solo la parte YYYY-MM-DD, no la hora exacta.
    return a[:10] == b[:10]


def main():
    if not os.path.exists(RUTA_OPORTUNIDADES):
        print("No existe ultimas_oportunidades_nuevas.json, nada que verificar.")
        return

    with open(RUTA_OPORTUNIDADES, 'r') as f:
        datos_oportunidades = json.load(f)

    oportunidades = datos_oportunidades.get("oportunidades", [])
    if not oportunidades:
        print("Sin oportunidades nuevas hoy, nada que verificar.")
        return

    fecha_oportunidades = datos_oportunidades.get("fecha", "")

    if os.path.exists(RUTA_VOLUMEN):
        with open(RUTA_VOLUMEN, 'r') as f:
            datos_volumen = json.load(f)
        if datos_volumen.get("enviado") and _misma_fecha(datos_volumen.get("fecha", ""), fecha_oportunidades):
            print("El volumen de búsqueda ya se envió correctamente hoy, nada que hacer.")
            return

    print("El volumen no llegó a tiempo (o falló en el camino) — mando el aviso simple de respaldo.")

    lineas = [f"• *[{o['origen']}]* {o['titulo']}" for o in oportunidades]
    texto = (
        f"📡 *Radar de Contenido Eléctrico* — {len(oportunidades)} oportunidad(es) nueva(s) "
        "(no se pudo calcular el volumen de búsqueda a tiempo)\n\n" + "\n".join(lineas)
    )

    webhook_url = os.getenv("SLACK_WORKFLOW_WEBHOOK_URL")
    if not webhook_url or webhook_url == "tu_url_de_webhook_aqui":
        print("Configura SLACK_WORKFLOW_WEBHOOK_URL para enviar el aviso de respaldo.")
        sys.exit(1)

    try:
        response = requests.post(webhook_url, json={"resumen": texto}, timeout=TIMEOUT_HTTP)
    except Exception as e:
        print(f"Error enviando petición a Slack: {e}")
        sys.exit(1)

    if response.status_code != 200:
        print(f"Error enviando a Slack (Status {response.status_code}): {response.text}")
        sys.exit(1)

    print(f"Aviso de respaldo enviado a Slack ({len(oportunidades)} oportunidad(es)).")


if __name__ == "__main__":
    main()
