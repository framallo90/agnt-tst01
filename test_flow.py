# test_flow.py
# Prueba de flujo completo para la gestión de proyectos y tareas con AgentePersonal

from agente_personal import AgentePersonal
import sqlite3
import sys

# --- Constantes de test ---
PROYECTO = "PruebaCI"  # Nombre del proyecto de prueba
CTX = "Contexto de prueba"  # Contexto asociado al proyecto
TAREA_1 = "Tarea 1 de prueba"  # Descripción de la tarea de prueba

# --- Funciones auxiliares para consulta directa en la base ---
def fetch_proyecto_id(conn, nombre):
    """Devuelve el id del proyecto dado su nombre."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM proyectos WHERE nombre=?", (nombre,))
    row = cur.fetchone()
    return row[0] if row else None

def fetch_tareas(conn, proyecto_id):
    """Devuelve todas las tareas asociadas a un proyecto."""
    cur = conn.cursor()
    cur.execute("SELECT id, descripcion, estado FROM tareas WHERE proyecto_id=?", (proyecto_id,))
    return cur.fetchall()

# --- Flujo principal de test ---
def main():
    ag = AgentePersonal()  # ya viene con check_same_thread=False y FK ON en tu versión mejorada
    try:
        # Asegura foreign keys (por si se cambia algo en el futuro)
        ag.conn.execute("PRAGMA foreign_keys = ON")

        # --- Limpieza previa del proyecto de test ---
        print("🧼 Limpiando rastro previo de", PROYECTO)
        cur = ag.conn.cursor()
        cur.execute("DELETE FROM tareas WHERE proyecto_id IN (SELECT id FROM proyectos WHERE nombre=?)", (PROYECTO,))
        cur.execute("DELETE FROM proyectos WHERE nombre=?", (PROYECTO,))
        ag.conn.commit()

        # --- Crear proyecto ---
        print("📁 Creando proyecto...")
        ag.crear_proyecto(PROYECTO, contexto=CTX)
        pid = fetch_proyecto_id(ag.conn, PROYECTO)
        assert pid is not None, "El proyecto no se creó correctamente."
        print(f"✅ Proyecto creado (id={pid})")

        # --- Agregar tarea ---
        print("📝 Agregando tarea...")
        ag.agregar_tarea(PROYECTO, TAREA_1)
        tareas = fetch_tareas(ag.conn, pid)
        assert len(tareas) == 1, f"Se esperaba 1 tarea, hay {len(tareas)}."
        assert tareas[0][1] == TAREA_1, "La descripción de la tarea no coincide."
        assert tareas[0][2] == "pendiente", "El estado inicial debe ser 'pendiente'."
        tid = tareas[0][0]
        print(f"✅ Tarea agregada (id={tid}, desc='{TAREA_1}', estado='pendiente')")

        # --- Actualizar estado a completada ---
        print("🔁 Marcando tarea como 'completada'...")
        ag.actualizar_estado_tarea(tid, "completada")
        tareas2 = fetch_tareas(ag.conn, pid)
        assert tareas2[0][2] == "completada", "El estado no se actualizó a 'completada'."
        print("✅ Tarea marcada como completada")

        # --- Listados finales (muestra) ---
        print("\n📋 Tareas del proyecto ahora:")
        for t in tareas2:
            print(f"  - id={t[0]} | desc={t[1]} | estado={t[2]}")

        print("\n🎉 Flujo OK.")
        return 0

    except AssertionError as e:
        print(f"\n❌ Test falló: {e}")
        return 1
    except Exception as e:
        print(f"\n💥 Error inesperado: {e}")
        return 2
    finally:
        try:
            ag.conn.close()
        except Exception:
            pass

# --- Ejecución directa del test ---
if __name__ == "__main__":
    sys.exit(main())
