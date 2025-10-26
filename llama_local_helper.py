
import os
from dotenv import load_dotenv
from llama_cpp import Llama


# Cargar variables del archivo .env automáticamente
load_dotenv()
MODEL_PATH = os.getenv('LLAMA_MODEL_PATH', 'models/llama-2-7b-chat.Q4_K_M.gguf')

llm = None

def cargar_modelo():
    global llm
    if llm is None:
        llm = Llama(model_path=MODEL_PATH, n_ctx=4096, verbose=False)


def obtener_respuesta_llama(mensajes, max_tokens=1024):
    """
    mensajes: lista de dicts [{'role': 'user'/'assistant', 'content': texto}]
    """
    cargar_modelo()
    prompt = "".join([
        ("Usuario: " if m['role']=='user' else "Asistente: ") + m['content'] + "\n"
        for m in mensajes
    ])
    prompt += "Asistente: "

    try:
        output = llm(prompt, max_tokens=max_tokens, temperature=0.7, stop=["Usuario:", "Asistente:"])
        respuesta = output['choices'][0]['text'].strip()
        return respuesta
    except Exception as e:
        return f"[Error al consultar modelo local: {e}]"


def obtener_respuesta_llama_stream(mensajes, callback, max_tokens=1024):
    """
    mensajes: lista de dicts [{'role': 'user'/'assistant', 'content': texto}]
    callback: función que recibe el texto parcial generado
    """
    cargar_modelo()
    prompt = "".join([
        ("Usuario: " if m['role']=='user' else "Asistente: ") + m['content'] + "\n"
        for m in mensajes
    ])
    prompt += "Asistente: "
    try:
        partial = ""
        vacio_count = 0
        for token in llm(prompt, max_tokens=max_tokens, temperature=0.7, stop=["Usuario:", "Asistente:"], stream=True):
            nuevo = token['choices'][0]['text']
            # Si el token es solo espacios o vacío, contar
            if not nuevo.strip():
                vacio_count += 1
                if vacio_count > 20:
                    aviso = "[El modelo está generando solo tokens vacíos. Se cortó la respuesta automática.]"
                    callback(aviso)
                    return aviso
                continue
            else:
                vacio_count = 0
            partial += nuevo
            callback(partial)
        return partial.strip()
    except Exception as e:
        callback(f"[Error al consultar modelo local: {e}]")
        return f"[Error al consultar modelo local: {e}]"
