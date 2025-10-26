import sqlite3
import threading
from typing import List, Tuple

DB_NAME = 'agente_personal.db'

class AgentePersonal:
    def __init__(self, db_path: str = DB_NAME):
        # Permite usar la conexión desde varios hilos y activa las claves foráneas
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        # Lock para serializar el acceso a la base de datos cuando se usa la misma
        # conexión desde múltiples hilos (evita condiciones de carrera y errores
        # como FOREIGN KEY constraint failed debido a escrituras concurrentes).
        self.lock = threading.Lock()
        self.conn.execute('PRAGMA foreign_keys = ON')
        self._crear_tablas()

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

if __name__ == '__main__':
    agente = AgentePersonal()
    print('Agente Personal listo para trabajar. Usá los métodos crear_proyecto, agregar_tarea y listar_tareas.')
