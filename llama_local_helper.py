# llama_local_helper.py
# Stub funcional para que la UI arranque. Reemplazalo por tu integración real cuando quieras.

import time

def obtener_respuesta_llama(historial):
    """
    Versión no-stream (opcional). Si ya tenías una integración real, dejala.
    Este stub solo devuelve una respuesta basada en el último turno del usuario.
    """
    ultimo_user = next((m["content"] for m in reversed(historial) if m["role"] == "user"), "")
    return f"Recibí tu mensaje: '{ultimo_user}'. (Respuesta demo no-stream)"

def obtener_respuesta_llama_stream(historial, callback, delay=0.08):
    """
    Stream básico: va enviando partes a `callback(texto_parcial)` y retorna el texto final.
    Si tenés una integración real (llama.cpp, ollama, etc.), llamá aquí y
    usá `callback` en cada chunk que recibas.
    """
    try:
        # Si tenés una versión real no-stream, podés reutilizarla
        base = obtener_respuesta_llama(historial)
    except Exception:
        base = "No pude generar respuesta (error interno)."

    # Simular streaming por chunks
    partes = ["⏳ Pensando… ", "OK, ", "ahora ", "te ", "respondo:\n", base]
    acumulado = ""
    for p in partes:
        acumulado += p
        callback(acumulado)
        time.sleep(delay)

    # Devuelve el texto final
    return acumulado
