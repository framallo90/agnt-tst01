from agente_personal import AgentePersonal

ag = AgentePersonal()
proyecto = 'PruebaCI'

# limpiar si existe
cursor = ag.conn.cursor()
cursor.execute('DELETE FROM tareas WHERE proyecto_id IN (SELECT id FROM proyectos WHERE nombre=?)', (proyecto,))
cursor.execute('DELETE FROM proyectos WHERE nombre=?', (proyecto,))
ag.conn.commit()

# crear proyecto
ag.crear_proyecto(proyecto, contexto='Contexto de prueba')
print('Proyecto creado')

# agregar tarea
ag.agregar_tarea(proyecto, 'Tarea 1 de prueba')
print('Tarea agregada')

# listar tareas
tareas = ag.listar_tareas(proyecto)
print('Tareas:', tareas)

# marcar completada
if tareas:
    tid = tareas[0][0]
    ag.actualizar_estado_tarea(tid, 'completada')
    print('Tarea marcada como completada')

# listar de nuevo
print('Tareas después:', ag.listar_tareas(proyecto))
