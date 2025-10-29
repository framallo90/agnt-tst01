from agente_personal import AgentePersonal
import threading, time

ag = AgentePersonal()
cur = ag.conn.cursor()
with ag.lock:
    cur.execute("DELETE FROM mensajes")
    cur.execute("DELETE FROM conversaciones")
    cur.execute("DELETE FROM tareas")
    cur.execute("DELETE FROM proyectos")
    ag.conn.commit()

with ag.lock:
    cur.execute("INSERT INTO proyectos (nombre) VALUES (?)", ("PROY_RACE",))
    ag.conn.commit()
    cur.execute("SELECT id FROM proyectos WHERE nombre=?", ("PROY_RACE",))
    pid = cur.fetchone()[0]
    cur.execute("INSERT INTO conversaciones (nombre, proyecto_id) VALUES (?, ?)", ("CHAT_RACE", pid))
    ag.conn.commit()
    cur.execute("SELECT id FROM conversaciones WHERE proyecto_id=?", (pid,))
    cid = cur.fetchone()[0]

print('Created', pid, cid)

# Background thread that waits and then inserts a message
def bg_insert():
    time.sleep(0.2)
    try:
        with ag.lock:
            cur2 = ag.conn.cursor()
            cur2.execute("INSERT INTO mensajes (conversacion_id, remitente, tipo, contenido) VALUES (?, ?, ?, ?)", (cid, 'Agente', 'texto', 'respuesta tardia'))
            ag.conn.commit()
            print('BG insert succeeded')
    except Exception as e:
        print('BG insert failed:', e)

t = threading.Thread(target=bg_insert)

t.start()

# Main thread deletes project immediately
with ag.lock:
    cur.execute('DELETE FROM proyectos WHERE id=?', (pid,))
    ag.conn.commit()

print('Main delete done')

t.join()

cur.execute('SELECT * FROM proyectos')
print('Proyectos:', cur.fetchall())
cur.execute('SELECT * FROM conversaciones')
print('Conversaciones:', cur.fetchall())
cur.execute('SELECT * FROM mensajes')
print('Mensajes:', cur.fetchall())
