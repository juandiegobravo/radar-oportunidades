from modulo_cnmc import detectar_altas_bajas_cnmc, diagnosticar_cnmc
from modulo_boe import consultar_boe, diagnosticar_boe
from modulo_competencia import detectar_content_gap
from modulo_sheets import guardar_en_sheets
from modulo_slack import enviar_resumen_slack
from progreso import mostrar_progreso

TOTAL_PASOS = 5  # CNMC, BOE, Rastreator, Selectra, Roams

def enviar_alerta_directa(origen, titulo_alerta, brecha_idea="", keywords="", resumen_slack=None):
    datos = {
        "Titulo Sugerido": titulo_alerta,
        "Idea Principal": brecha_idea,
        "Palabras Clave": keywords
    }
    guardar_en_sheets(origen, datos)
    if resumen_slack is not None:
        resumen_slack.append({"origen": origen, "titulo": titulo_alerta})

def main():
    print("Iniciando Radar de Contenido Eléctrico...")
    print("\n--- INICIO DIAGNÓSTICO DE LECTURA ---")
    diagnosticar_cnmc()
    diagnosticar_boe()
    print("--- FIN DIAGNÓSTICO DE LECTURA ---\n")

    paso = 0
    resumen_slack = []

    # 1. Módulo CNMC: altas y bajas de comercializadoras
    print("Revisando CNMC (altas y bajas)...")
    alertas_cnmc = detectar_altas_bajas_cnmc()
    if alertas_cnmc:
        for alerta in alertas_cnmc:
            print(f"  -> {alerta['titulo']}")
            enviar_alerta_directa("CNMC", alerta["titulo"], alerta["detalle"], resumen_slack=resumen_slack)
        print(f"CNMC: {len(alertas_cnmc)} alerta(s) enviada(s) a Sheet1.")
    else:
        print("CNMC: sin altas ni bajas nuevas.")
    paso += 1
    mostrar_progreso(paso, TOTAL_PASOS, "CNMC")

    # 2. Módulo BOE
    print("Revisando BOE...")
    novedades_boe = consultar_boe()
    if novedades_boe:
        for nov in novedades_boe:
            print(f"  -> {nov['titulo']}")
            enviar_alerta_directa("BOE", nov["titulo"], resumen_slack=resumen_slack)
        print(f"BOE: {len(novedades_boe)} novedad(es) enviada(s) a Sheet1.")
    else:
        print("BOE: sin novedades relevantes.")
    paso += 1
    mostrar_progreso(paso, TOTAL_PASOS, "BOE")

    # 3. Módulo Competencia: análisis de brechas de contenido
    print("Revisando Competencia (Rastreator, Selectra, Roams vs Papernest)...")

    def _avance_competencia(origen):
        nonlocal paso
        paso += 1
        mostrar_progreso(paso, TOTAL_PASOS, f"Competencia: {origen}")

    gaps = detectar_content_gap(progreso_callback=_avance_competencia)
    if gaps:
        for gap in gaps:
            titulo_alerta = f"Nueva idea de contenido identificada: {gap['titulo']}"
            brecha = f"Detectado en {gap['origen']} y no cubierto por Papernest."
            print(f"  -> {titulo_alerta}")
            enviar_alerta_directa("Competencia", titulo_alerta, brecha, resumen_slack=resumen_slack)
        print(f"Competencia: {len(gaps)} brecha(s) de contenido nueva(s) detectada(s).")
    else:
        print("Competencia: sin brechas de contenido nuevas.")

    enviar_resumen_slack(resumen_slack)
    print("Radar completado.")

if __name__ == "__main__":
    main()
