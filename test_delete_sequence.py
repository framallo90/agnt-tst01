from agente_personal import AgentePersonal
import sqlite3

ag = AgentePersonal()
cur = ag.conn.cursor()

# Cleanup test artifacts
cur.execute("DELETE FROM mensajes")
cur.execute("DELETE FROM conversaciones")
cur.execute("DELETE FROM tareas")
cur.execute("DELETE FROM proyectos")
ag.conn.commit()

# Create project
cur.execute("INSERT INTO proyectos (nombre, contexto) VALUES (?, ?)", ("PROY_DEL_TEST", "ctx"))
ag.conn.commit()
cur.execute("SELECT id FROM proyectos WHERE nombre=?", ("PROY_DEL_TEST",))
proj_id = cur.fetchone()[0]
print('Created project', proj_id)

# Create conversation under project
cur.execute("INSERT INTO conversaciones (nombre, proyecto_id) VALUES (?, ?)", ("CHAT_TEST", proj_id))
ag.conn.commit()
cur.execute("SELECT id FROM conversaciones WHERE proyecto_id=?", (proj_id,))
conv_id = cur.fetchone()[0]
print('Created conversation', conv_id)

# Create message under conversation
cur.execute("INSERT INTO mensajes (conversacion_id, remitente, tipo, contenido) VALUES (?, ?, ?, ?)", (conv_id, 'Usuario', 'texto', 'hola'))
ag.conn.commit()
cur.execute("SELECT id FROM mensajes WHERE conversacion_id=?", (conv_id,))
print('Messages for conv:', [r[0] for r in cur.fetchall()])

# Now attempt deletion using a single DELETE relying on cascade
try:
    cur.execute('DELETE FROM proyectos WHERE id=?', (proj_id,))
    ag.conn.commit()
    print('Deletion succeeded (cascade)')
except Exception as e:
    print('Deletion failed:', repr(e))

# Check remaining tables
cur.execute("SELECT * FROM proyectos")
print('Proyectos:', cur.fetchall())
cur.execute("SELECT * FROM conversaciones")
print('Conversaciones:', cur.fetchall())
cur.execute("SELECT * FROM mensajes")
print('Mensajes:', cur.fetchall())

# Clean up
cur.execute("DELETE FROM mensajes")
cur.execute("DELETE FROM conversaciones")
cur.execute("DELETE FROM tareas")
cur.execute("DELETE FROM proyectos")
ag.conn.commit()
print('Cleanup done')
