import sqlite3, os

db='agente_personal.db'
print('Ruta actual:', os.getcwd())
print('Existe DB?', os.path.exists(db))
if os.path.exists(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cur.fetchall()
    print('Tablas encontradas:', tables)
    conn.close()
else:
    print('No se encontró la base de datos.')
