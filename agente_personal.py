import sqlite3
import threading
from typing import List, Tuple

DB_NAME = 'agente_personal.db'

class AgentePersonal:
    def __init__(self, db_path: str = DB_NAME, perform_migration: bool = True):
        # Permite usar la conexión desde varios hilos y activa las claves foráneas
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        # Reducir tiempos de espera en locks para no bloquear la UI al iniciar
        try:
            self.conn.execute('PRAGMA busy_timeout = 250')  # ms
        except Exception:
            pass
        # Lock para serializar el acceso a la base de datos cuando se usa la misma
        # conexión desde múltiples hilos (evita condiciones de carrera y errores
        # como FOREIGN KEY constraint failed debido a escrituras concurrentes).
        self.lock = threading.Lock()
        self.conn.execute('PRAGMA foreign_keys = ON')
        self._crear_tablas()
        # Migración automática: opcional para evitar bloquear la UI en el hilo principal.
        if perform_migration:
            # Si la BD fue creada sin ON DELETE CASCADE, reconstruimos las tablas dependientes
            # para habilitar la cascada.
            self._migrar_cascada_si_falta()

    def _crear_tablas(self):
        cursor = self.conn.cursor()
        # Proyectos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS proyectos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL,
                contexto TEXT
            )
        ''')
        # Tareas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tareas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                descripcion TEXT NOT NULL,
                estado TEXT DEFAULT 'pendiente',
                FOREIGN KEY(proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE
            )
        ''')
        # Conversaciones (pueden ser libres o asociadas a un proyecto)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                proyecto_id INTEGER,
                fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE
            )
        ''')
        # Mensajes (texto o voz)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mensajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversacion_id INTEGER NOT NULL,
                remitente TEXT NOT NULL,
                tipo TEXT NOT NULL, -- 'texto' o 'voz'
                contenido TEXT NOT NULL,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(conversacion_id) REFERENCES conversaciones(id) ON DELETE CASCADE
            )
        ''')
        self.conn.commit()

    # --- MIGRACIÓN DE ESQUEMA: habilitar ON DELETE CASCADE si falta ---
    def _tiene_cascada(self, tabla: str) -> bool:
        """Devuelve True si TODAS las FKs de la tabla usan ON DELETE CASCADE."""
        cur = self.conn.cursor()
        try:
            fks = cur.execute(f'PRAGMA foreign_key_list({tabla})').fetchall()
        except Exception:
            return False
        if not fks:
            return True  # no tiene FKs
        # PRAGMA foreign_key_list columns: id,seq,table,from,to,on_update,on_delete,match
        # We must check on_delete (index 6), not on_update (index 5)
        return all((len(row) >= 7 and (row[6] or '').upper() == 'CASCADE') for row in fks)

    def _limpiar_huerfanos(self):
        """Elimina registros huérfanos en caso de que existan por falta histórica de FKs."""
        cur = self.conn.cursor()
        # Conversaciones sin proyecto válido
        cur.execute("DELETE FROM conversaciones WHERE proyecto_id IS NOT NULL AND proyecto_id NOT IN (SELECT id FROM proyectos)")
        # Mensajes sin conversación válida
        cur.execute("DELETE FROM mensajes WHERE conversacion_id NOT IN (SELECT id FROM conversaciones)")

    def _migrar_cascada_si_falta(self):
        """Reconstruye tablas con ON DELETE CASCADE si el esquema actual no lo tiene.

        Pasos:
          1) Desactivar enforcement de FKs para poder recrear.
          2) Crear tablas *_new con el esquema correcto.
          3) Copiar datos existentes.
          4) Reemplazar tablas.
          5) Limpiar huérfanos y reactivar FKs.
        """
        # Si todas las tablas ya tienen cascada, nada que hacer
        if self._tiene_cascada('tareas') and self._tiene_cascada('conversaciones') and self._tiene_cascada('mensajes'):
            return

        with self.lock:
            cur = self.conn.cursor()
            cur.execute('PRAGMA foreign_keys = OFF')
            try:
                cur.execute('BEGIN IMMEDIATE')

                # --- tareas ---
                if not self._tiene_cascada('tareas'):
                    cur.execute('''
                        CREATE TABLE IF NOT EXISTS tareas_new (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            proyecto_id INTEGER NOT NULL,
                            descripcion TEXT NOT NULL,
                            estado TEXT DEFAULT 'pendiente',
                            FOREIGN KEY(proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE
                        )
                    ''')
                    cur.execute(
                        """
                        INSERT INTO tareas_new (id, proyecto_id, descripcion, estado)
                        SELECT id, proyecto_id, descripcion, estado FROM tareas
                        """
                    )
                    cur.execute('DROP TABLE tareas')
                    cur.execute('ALTER TABLE tareas_new RENAME TO tareas')

                # --- conversaciones ---
                if not self._tiene_cascada('conversaciones'):
                    cur.execute('''
                        CREATE TABLE IF NOT EXISTS conversaciones_new (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            nombre TEXT,
                            proyecto_id INTEGER,
                            fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY(proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE
                        )
                    ''')
                    cur.execute(
                        """
                        INSERT INTO conversaciones_new (id, nombre, proyecto_id, fecha_inicio)
                        SELECT id, nombre, proyecto_id, fecha_inicio FROM conversaciones
                        """
                    )
                    cur.execute('DROP TABLE conversaciones')
                    cur.execute('ALTER TABLE conversaciones_new RENAME TO conversaciones')

                # --- mensajes ---
                if not self._tiene_cascada('mensajes'):
                    cur.execute('''
                        CREATE TABLE IF NOT EXISTS mensajes_new (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            conversacion_id INTEGER NOT NULL,
                            remitente TEXT NOT NULL,
                            tipo TEXT NOT NULL,
                            contenido TEXT NOT NULL,
                            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY(conversacion_id) REFERENCES conversaciones(id) ON DELETE CASCADE
                        )
                    ''')
                    cur.execute(
                        """
                        INSERT INTO mensajes_new (id, conversacion_id, remitente, tipo, contenido, fecha)
                        SELECT id, conversacion_id, remitente, tipo, contenido, fecha FROM mensajes
                        """
                    )
                    cur.execute('DROP TABLE mensajes')
                    cur.execute('ALTER TABLE mensajes_new RENAME TO mensajes')

                # Limpiar huérfanos que pudieran venir del esquema anterior
                self._limpiar_huerfanos()

                cur.execute('COMMIT')
            except Exception:
                cur.execute('ROLLBACK')
                raise
            finally:
                # Reactivar enforcement y asegurar ON
                cur.execute('PRAGMA foreign_keys = ON')
                self.conn.commit()

    def crear_proyecto(self, nombre: str, contexto: str = None):
        cursor = self.conn.cursor()
        cursor.execute('INSERT INTO proyectos (nombre, contexto) VALUES (?, ?)', (nombre, contexto))
        self.conn.commit()

    def agregar_tarea(self, proyecto: str, tarea: str):
        cursor = self.conn.cursor()
        cursor.execute('SELECT id FROM proyectos WHERE nombre = ?', (proyecto,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Proyecto '{proyecto}' no existe.")
        proyecto_id = row[0]
        cursor.execute('INSERT INTO tareas (proyecto_id, descripcion) VALUES (?, ?)', (proyecto_id, tarea))
        self.conn.commit()

    def listar_tareas(self, proyecto: str) -> List[Tuple[int, str, str]]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT id FROM proyectos WHERE nombre = ?', (proyecto,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Proyecto '{proyecto}' no existe.")
        proyecto_id = row[0]
        cursor.execute('SELECT id, descripcion, estado FROM tareas WHERE proyecto_id = ?', (proyecto_id,))
        return cursor.fetchall()

    def actualizar_estado_tarea(self, tarea_id: int, nuevo_estado: str):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE tareas SET estado = ? WHERE id = ?', (nuevo_estado, tarea_id))
        self.conn.commit()

    def cargar_contexto(self, proyecto: str) -> str:
        cursor = self.conn.cursor()
        cursor.execute('SELECT contexto FROM proyectos WHERE nombre = ?', (proyecto,))
        row = cursor.fetchone()
        if row:
            return row[0]
        return None

    def listar_mensajes(self, conversacion_id: int) -> List[Tuple[str, str]]:
        """Devuelve (remitente, contenido) de una conversación ordenados por fecha e id.

        Se ejecuta bajo lock para evitar condiciones de carrera con otros hilos que
        escriban/lean simultáneamente en la misma conexión SQLite.
        """
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                'SELECT remitente, contenido FROM mensajes WHERE conversacion_id = ? '
                'ORDER BY datetime(fecha) ASC, id ASC',
                (conversacion_id,)
            )
            return cur.fetchall()

if __name__ == '__main__':
    agente = AgentePersonal()
    print('Agente Personal listo para trabajar. Usá los métodos crear_proyecto, agregar_tarea y listar_tareas.')
