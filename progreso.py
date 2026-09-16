import threading
import time

ANCHO_BARRA = 30

def mostrar_progreso(actual, total, etiqueta=""):
    fraccion = min(actual / total, 1) if total else 1
    llenado = int(ANCHO_BARRA * fraccion)
    barra = '#' * llenado + '-' * (ANCHO_BARRA - llenado)
    linea = f"\r[{barra}] {int(fraccion * 100)}% ({actual}/{total}) {etiqueta}"
    print(linea.ljust(80), end='', flush=True)
    if actual >= total:
        print()

def iniciar_cronometro(etiqueta):
    """
    Arranca un contador de segundos que se refresca en la misma línea de la
    terminal mientras dura una operación bloqueante (ej. esperar a la IA).
    Devuelve una función que hay que llamar al terminar: detiene el hilo,
    imprime el tiempo final y lo retorna en segundos.
    """
    detener_evento = threading.Event()
    inicio = time.time()

    def _tick():
        while not detener_evento.is_set():
            transcurrido = time.time() - inicio
            print(f"\r{etiqueta}... {transcurrido:.1f}s".ljust(80), end='', flush=True)
            detener_evento.wait(0.5)

    hilo = threading.Thread(target=_tick, daemon=True)
    hilo.start()

    def _detener():
        detener_evento.set()
        hilo.join()
        transcurrido = time.time() - inicio
        print(f"\r{etiqueta}: {transcurrido:.1f}s".ljust(80))
        return transcurrido

    return _detener
