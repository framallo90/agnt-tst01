"""Integración local con LLaMA usando un archivo GGUF y fallback seguro.

Requisitos recomendados (CPU):
  pip install llama-cpp-python

Archivo esperado: ./llama-2-7b-chat.Q4_K_M.gguf (ver .gitignore)
Si no está la librería o el archivo, se usa un stub de respaldo para que la UI nunca quede colgada.
"""

import os
import time
import threading
from typing import List, Dict, Callable, Optional

_MODEL_FILENAME = "llama-2-7b-chat.Q4_K_M.gguf"
_MODEL_PATH = os.path.join(os.path.dirname(__file__), _MODEL_FILENAME)

try:
    from llama_cpp import Llama  # type: ignore
except Exception:  # librería no disponible
    Llama = None  # type: ignore

_llm = None  # type: ignore
_llm_lock = threading.Lock()


def _get_llm() -> Optional[object]:
    """Carga perezosa del modelo local si está disponible; de lo contrario None."""
    global _llm
    if _llm is not None:
        return _llm
    if Llama is None or not os.path.exists(_MODEL_PATH):
        return None
    with _llm_lock:
        if _llm is None:
            # Config básica; ajustar n_ctx/n_threads según tu equipo
            _llm = Llama(model_path=_MODEL_PATH, n_ctx=4096, n_threads=os.cpu_count() or 4)
    return _llm


def _to_chat_messages(historial: List[Dict[str, str]]) -> List[Dict[str, str]]:
    # Filtrar roles conocidos y mantener orden
    msgs = []
    for m in historial:
        role = m.get("role", "user")
        if role not in {"user", "assistant", "system"}:
            role = "user"
        msgs.append({"role": role, "content": m.get("content", "")})
    return msgs


def obtener_respuesta_llama(historial: List[Dict[str, str]]) -> str:
    """Camino no-stream: usa llama-cpp si está disponible; fallback si no."""
    llm = _get_llm()
    # Inyectar sistema para español y saludo personalizado
    system_prompt = {"role": "system", "content": "Responde siempre en español y llama al usuario Facu en tus respuestas."}
    messages = [system_prompt] + _to_chat_messages(historial)
    if llm is None:
        # Fallback estable
        ultimo_user = next((m["content"] for m in reversed(historial) if m.get("role") == "user"), "")
        return f"Hola Facu, recibí tu mensaje: '{ultimo_user}'. (Respuesta demo no-stream)"
    try:
        out = llm.create_chat_completion(messages=messages, max_tokens=512)
        return out["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[Error LLaMA] {e}"


def obtener_respuesta_llama_stream(historial: List[Dict[str, str]], callback: Callable[[str], None], delay: float = 0.0) -> str:
    """Camino stream: devuelve texto final y publica parciales en callback."""
    llm = _get_llm()
    # Inyectar sistema para español y saludo personalizado
    system_prompt = {"role": "system", "content": "Responde siempre en español y llama al usuario Facu en tus respuestas."}
    messages = [system_prompt] + _to_chat_messages(historial)

    if llm is None:
        # Fallback a no-stream con particionado simple para simular streaming
        base = obtener_respuesta_llama(historial)
        partes = ["⏳ Pensando… ", "OK, ", "ahora ", "te ", "respondo:\n", base]
        acumulado = ""
        for p in partes:
            acumulado += p
            try:
                callback(acumulado)
            except Exception:
                pass
            if delay:
                time.sleep(delay)
        return acumulado

    acumulado = ""
    try:
        for chunk in llm.create_chat_completion(messages=messages, stream=True, max_tokens=512):
            delta = ""
            try:
                delta = chunk["choices"][0]["delta"].get("content", "")
            except Exception:
                # Compatibilidad con versiones que usan 'text' durante el stream
                delta = chunk["choices"][0].get("text", "")
            if not delta:
                continue
            acumulado += delta
            try:
                callback(acumulado)
            except Exception:
                pass
            if delay:
                time.sleep(delay)
    except Exception as e:
        acumulado = f"[Error LLaMA stream] {e}"
        try:
            callback(acumulado)
        except Exception:
            pass
    return acumulado
