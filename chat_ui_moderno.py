import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from agente_personal import AgentePersonal
from llama_local_helper import obtener_respuesta_llama
import threading
import sqlite3
import queue

DARK_BG = '#23272f'
DARK_PANEL = '#181a20'
DARK_ACCENT = '#2d313a'
USER_BUBBLE = '#3a7afe'
AGENT_BUBBLE = '#444c56'
TEXT_COLOR = '#f5f6fa'
FONT = ('Segoe UI', 11)

class ChatModernUI:
    def __init__(self, root):
        self.root = root
        self.root.title('Agente Personal - Chat Moderno')
        self.root.configure(bg=DARK_BG)
        self.agente = AgentePersonal()
        self.proyecto_actual = None
        self.conversacion_id = None
        self._build_ui()
        self._cargar_proyectos()
        self.respuesta_queue = queue.Queue()
        self._chequear_respuesta()

    def _build_ui(self):
        self.root.geometry('900x600')
        self.root.minsize(700, 400)
        self.frame_main = tk.Frame(self.root, bg=DARK_BG)
        self.frame_main.pack(fill='both', expand=True)

        # Área de chat (antes del menú lateral para asegurar visibilidad)
        self.frame_chat = tk.Frame(self.frame_main, bg=DARK_BG)
        self.frame_chat.pack(side='right', fill='both', expand=True)

        self.canvas = tk.Canvas(self.frame_chat, bg=DARK_BG, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.frame_chat, orient='vertical', command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=DARK_BG)
        self.scrollable_frame.bind(
            '<Configure>',
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        )
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side='left', fill='both', expand=True, padx=(0,0), pady=(0,0))
        self.scrollbar.pack(side='right', fill='y')
        # Bind para la rueda del mouse (Windows y Linux)
        self.canvas.bind('<MouseWheel>', self._on_mousewheel)  # Windows
        self.canvas.bind('<Button-4>', self._on_mousewheel)    # Linux scroll up
        self.canvas.bind('<Button-5>', self._on_mousewheel)    # Linux scroll down

        # Input siempre fijo abajo
        self.frame_input = tk.Frame(self.root, bg=DARK_PANEL)
        self.frame_input.pack(side='bottom', fill='x')
        self.entry_msg = tk.Entry(self.frame_input, font=FONT, bg=DARK_ACCENT, fg=TEXT_COLOR, insertbackground=TEXT_COLOR, relief='flat')
        self.entry_msg.pack(side='left', padx=(20,5), pady=15, fill='x', expand=True)
        self.entry_msg.bind('<Return>', self.enviar_mensaje)
        self.btn_microfono = tk.Button(self.frame_input, text='🎤', font=('Segoe UI Emoji', 12), bg='#b83a3a', fg='white', relief='flat', command=self.dictar_mensaje)
        self.btn_microfono.pack(side='left', padx=5)
        self.btn_enviar = tk.Button(self.frame_input, text='Enviar', bg=USER_BUBBLE, fg='white', font=FONT, relief='flat', command=self.enviar_mensaje, activebackground='#2556b8')
        self.btn_enviar.pack(side='left', padx=(5,20))

        # Menú lateral
        self.frame_menu = tk.Frame(self.frame_main, bg=DARK_PANEL, width=200)
        self.frame_menu.pack(side='left', fill='y')
        self.frame_menu.pack_propagate(False)

    lbl_proyectos = tk.Label(self.frame_menu, text='Proyectos', bg=DARK_PANEL, fg=TEXT_COLOR, font=('Segoe UI', 12, 'bold'))
    lbl_proyectos.pack(pady=(20,10))

    self.listbox_proyectos = tk.Listbox(self.frame_menu, bg=DARK_ACCENT, fg=TEXT_COLOR, selectbackground=USER_BUBBLE, selectforeground=TEXT_COLOR, relief='flat', font=FONT, highlightthickness=0)
    self.listbox_proyectos.pack(fill='y', expand=True, padx=10)
    self.listbox_proyectos.bind('<<ListboxSelect>>', self.seleccionar_proyecto)

    # Panel de chats por proyecto (dentro de __init__)
    self.frame_chats = tk.Frame(self.frame_menu, bg=DARK_PANEL)
    self.frame_chats.pack(fill='x', padx=10, pady=(5,10))
    self.lbl_chats = tk.Label(self.frame_chats, text='Chats', bg=DARK_PANEL, fg=TEXT_COLOR, font=('Segoe UI', 11, 'bold'))
    self.lbl_chats.pack(pady=(5,2))
    self.listbox_chats = tk.Listbox(self.frame_chats, bg=DARK_ACCENT, fg=TEXT_COLOR, selectbackground=AGENT_BUBBLE, selectforeground=TEXT_COLOR, relief='flat', font=FONT, highlightthickness=0, height=6)
    self.listbox_chats.pack(fill='x', padx=2)
    self.listbox_chats.bind('<<ListboxSelect>>', self.seleccionar_chat)
    btn_nuevo_chat = tk.Button(self.frame_chats, text='+ Nuevo Chat', bg=USER_BUBBLE, fg='white', font=FONT, relief='flat', command=self.crear_chat, activebackground='#2556b8')
    btn_nuevo_chat.pack(pady=(5,2), fill='x')
    btn_renombrar_chat = tk.Button(self.frame_chats, text='✏️ Renombrar Chat', bg=DARK_ACCENT, fg=TEXT_COLOR, font=FONT, relief='flat', command=self.renombrar_chat, activebackground=USER_BUBBLE)
    btn_renombrar_chat.pack(pady=(2,2), fill='x')
    btn_eliminar_chat = tk.Button(self.frame_chats, text='🗑 Eliminar Chat', bg='#b83a3a', fg='white', font=FONT, relief='flat', command=self.eliminar_chat, activebackground='#7a2323')
    btn_eliminar_chat.pack(pady=(2,2), fill='x')
    def _cargar_chats(self, proyecto_id):
        self.listbox_chats.delete(0, tk.END)
        cursor = self.agente.conn.cursor()
        cursor.execute('SELECT id, nombre FROM conversaciones WHERE proyecto_id = ? ORDER BY fecha_inicio DESC', (proyecto_id,))
        chats = cursor.fetchall()
        for chat_id, nombre in chats:
            self.listbox_chats.insert(tk.END, nombre or f'Chat {chat_id}')
        if chats:
            self.listbox_chats.selection_set(0)
            self.seleccionar_chat()
        else:
            self.conversacion_id = None
            self._cargar_historial()

    def crear_chat(self):
        seleccion = self.listbox_proyectos.curselection()
        if not seleccion:
            messagebox.showinfo('Nuevo Chat', 'Seleccioná un proyecto primero.')
            return
        nombre_proyecto = self.listbox_proyectos.get(seleccion[0])
        cursor = self.agente.conn.cursor()
        cursor.execute('SELECT id FROM proyectos WHERE nombre = ?', (nombre_proyecto,))
        row = cursor.fetchone()
        if row:
            proyecto_id = row[0]
            nombre = simpledialog.askstring('Nuevo Chat', 'Nombre del chat:')
            cursor.execute('INSERT INTO conversaciones (nombre, proyecto_id) VALUES (?, ?)', (nombre, proyecto_id))
            self.agente.conn.commit()
            self._cargar_chats(proyecto_id)

    def renombrar_chat(self):
        seleccion = self.listbox_chats.curselection()
        if not seleccion:
            messagebox.showinfo('Renombrar Chat', 'Seleccioná un chat para renombrar.')
            return
        nombre_chat = self.listbox_chats.get(seleccion[0])
        seleccion_proy = self.listbox_proyectos.curselection()
        if not seleccion_proy:
            return
        nombre_proyecto = self.listbox_proyectos.get(seleccion_proy[0])
        cursor = self.agente.conn.cursor()
        cursor.execute('SELECT id FROM conversaciones WHERE nombre = ? AND proyecto_id = (SELECT id FROM proyectos WHERE nombre = ?)', (nombre_chat, nombre_proyecto))
        row = cursor.fetchone()
        if row:
            chat_id = row[0]
            nuevo_nombre = simpledialog.askstring('Renombrar Chat', f'Nuevo nombre para "{nombre_chat}":')
            if nuevo_nombre and nuevo_nombre != nombre_chat:
                cursor.execute('UPDATE conversaciones SET nombre = ? WHERE id = ?', (nuevo_nombre, chat_id))
                self.agente.conn.commit()
                self._cargar_chats(row[0])

    def eliminar_chat(self):
        seleccion = self.listbox_chats.curselection()
        if not seleccion:
            messagebox.showinfo('Eliminar Chat', 'Seleccioná un chat para eliminar.')
            return
        nombre_chat = self.listbox_chats.get(seleccion[0])
        seleccion_proy = self.listbox_proyectos.curselection()
        if not seleccion_proy:
            return
        nombre_proyecto = self.listbox_proyectos.get(seleccion_proy[0])
        cursor = self.agente.conn.cursor()
        cursor.execute('SELECT id FROM conversaciones WHERE nombre = ? AND proyecto_id = (SELECT id FROM proyectos WHERE nombre = ?)', (nombre_chat, nombre_proyecto))
        row = cursor.fetchone()
        if row:
            chat_id = row[0]
            if messagebox.askyesno('Eliminar Chat', f'¿Seguro que querés eliminar el chat "{nombre_chat}" y todo su historial?'):
                cursor.execute('DELETE FROM mensajes WHERE conversacion_id = ?', (chat_id,))
                cursor.execute('DELETE FROM conversaciones WHERE id = ?', (chat_id,))
                self.agente.conn.commit()
                self._cargar_chats(row[0])

    def seleccionar_chat(self, event=None):
        seleccion = self.listbox_chats.curselection()
        if not seleccion:
            self.conversacion_id = None
            self._cargar_historial()
            return
        nombre_chat = self.listbox_chats.get(seleccion[0])
        seleccion_proy = self.listbox_proyectos.curselection()
        if not seleccion_proy:
            return
        nombre_proyecto = self.listbox_proyectos.get(seleccion_proy[0])
        cursor = self.agente.conn.cursor()
        cursor.execute('SELECT id FROM conversaciones WHERE nombre = ? AND proyecto_id = (SELECT id FROM proyectos WHERE nombre = ?)', (nombre_chat, nombre_proyecto))
        row = cursor.fetchone()
        if row:
            self.conversacion_id = row[0]
            self._cargar_historial()

        btn_nuevo = tk.Button(self.frame_menu, text='+ Nuevo Proyecto', bg=USER_BUBBLE, fg='white', font=FONT, relief='flat', command=self.crear_proyecto, activebackground='#2556b8')
        btn_nuevo.pack(pady=(10,5), padx=10, fill='x')

        btn_renombrar = tk.Button(self.frame_menu, text='✏️ Renombrar Proyecto', bg=DARK_ACCENT, fg=TEXT_COLOR, font=FONT, relief='flat', command=self.renombrar_proyecto, activebackground=USER_BUBBLE)
        btn_renombrar.pack(pady=(5,5), padx=10, fill='x')

        btn_eliminar = tk.Button(self.frame_menu, text='🗑 Eliminar Proyecto', bg='#b83a3a', fg='white', font=FONT, relief='flat', command=self.eliminar_proyecto, activebackground='#7a2323')
        btn_eliminar.pack(pady=(5,5), padx=10, fill='x')

        btn_borrar_hist = tk.Button(self.frame_menu, text='🗑 Borrar Historial', bg='#b83a3a', fg='white', font=FONT, relief='flat', command=self.borrar_historial, activebackground='#7a2323')
        btn_borrar_hist.pack(pady=(5,15), padx=10, fill='x')
    def renombrar_proyecto(self):
        seleccion = self.listbox_proyectos.curselection()
        if not seleccion:
            messagebox.showinfo('Renombrar', 'Seleccioná un proyecto para renombrar.')
            return
        nombre_actual = self.listbox_proyectos.get(seleccion[0])
        nuevo_nombre = simpledialog.askstring('Renombrar Proyecto', f'Nuevo nombre para "{nombre_actual}":')
        if nuevo_nombre and nuevo_nombre != nombre_actual:
            cursor = self.agente.conn.cursor()
            cursor.execute('UPDATE proyectos SET nombre = ? WHERE nombre = ?', (nuevo_nombre, nombre_actual))
            self.agente.conn.commit()
            self._cargar_proyectos()
            messagebox.showinfo('Renombrado', f'Proyecto renombrado a "{nuevo_nombre}".')

    def eliminar_proyecto(self):
        seleccion = self.listbox_proyectos.curselection()
        if not seleccion:
            messagebox.showinfo('Eliminar', 'Seleccioná un proyecto para eliminar.')
            return
        nombre = self.listbox_proyectos.get(seleccion[0])
        if messagebox.askyesno('Eliminar Proyecto', f'¿Seguro que querés eliminar el proyecto "{nombre}" y todo su historial?'):
            cursor = self.agente.conn.cursor()
            # Eliminar mensajes y conversaciones asociadas
            cursor.execute('SELECT id FROM proyectos WHERE nombre = ?', (nombre,))
            row = cursor.fetchone()
            if row:
                proyecto_id = row[0]
                cursor.execute('SELECT id FROM conversaciones WHERE proyecto_id = ?', (proyecto_id,))
                convs = cursor.fetchall()
                for conv in convs:
                    conv_id = conv[0]
                    cursor.execute('DELETE FROM mensajes WHERE conversacion_id = ?', (conv_id,))
                    cursor.execute('DELETE FROM conversaciones WHERE id = ?', (conv_id,))
                cursor.execute('DELETE FROM proyectos WHERE id = ?', (proyecto_id,))
                self.agente.conn.commit()
                self._cargar_proyectos()
                messagebox.showinfo('Eliminado', f'Proyecto "{nombre}" eliminado.')

        # Área de chat
        self.frame_chat = tk.Frame(self.frame_main, bg=DARK_BG)
        self.frame_chat.pack(side='left', fill='both', expand=True)

        self.canvas = tk.Canvas(self.frame_chat, bg=DARK_BG, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.frame_chat, orient='vertical', command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=DARK_BG)
        self.scrollable_frame.bind(
            '<Configure>',
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        )
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side='left', fill='both', expand=True, padx=(0,0), pady=(0,0))
        self.scrollbar.pack(side='right', fill='y')

        # Input
        self.frame_input = tk.Frame(self.root, bg=DARK_PANEL)
        self.frame_input.pack(side='bottom', fill='x')
        self.entry_msg = tk.Entry(self.frame_input, font=FONT, bg=DARK_ACCENT, fg=TEXT_COLOR, insertbackground=TEXT_COLOR, relief='flat')
        self.entry_msg.pack(side='left', padx=(20,5), pady=15, fill='x', expand=True)
        self.entry_msg.bind('<Return>', self.enviar_mensaje)
        self.btn_microfono = tk.Button(self.frame_input, text='🎤', font=('Segoe UI Emoji', 12), bg=DARK_ACCENT, fg=TEXT_COLOR, relief='flat', command=self.dictar_mensaje)
        self.btn_microfono.pack(side='left', padx=5)
        self.btn_enviar = tk.Button(self.frame_input, text='Enviar', bg=USER_BUBBLE, fg='white', font=FONT, relief='flat', command=self.enviar_mensaje, activebackground='#2556b8')
        self.btn_enviar.pack(side='left', padx=(5,20))

    def _cargar_proyectos(self):
        self.listbox_proyectos.delete(0, tk.END)
        cursor = self.agente.conn.cursor()
        cursor.execute('SELECT nombre FROM proyectos ORDER BY nombre ASC')
        proyectos = [row[0] for row in cursor.fetchall()]
        for p in proyectos:
            self.listbox_proyectos.insert(tk.END, p)
        if proyectos:
            self.listbox_proyectos.selection_set(0)
            self.seleccionar_proyecto()
        else:
            self._nueva_conversacion_libre()

    def crear_proyecto(self):
        nombre = simpledialog.askstring('Nuevo Proyecto', 'Nombre del proyecto:')
        if nombre:
            try:
                self.agente.crear_proyecto(nombre)
                self._cargar_proyectos()
            except Exception as e:
                messagebox.showerror('Error', str(e))

    def seleccionar_proyecto(self, event=None):
        seleccion = self.listbox_proyectos.curselection()
        if not seleccion:
            self._nueva_conversacion_libre()
            return
        nombre = self.listbox_proyectos.get(seleccion[0])
        cursor = self.agente.conn.cursor()
        cursor.execute('SELECT id FROM proyectos WHERE nombre = ?', (nombre,))
        row = cursor.fetchone()
        if row:
            proyecto_id = row[0]
            self.proyecto_actual = nombre
            self._cargar_chats(proyecto_id)

    def _nueva_conversacion_libre(self):
        cursor = self.agente.conn.cursor()
        cursor.execute('INSERT INTO conversaciones (nombre, proyecto_id) VALUES (?, ?)', (None, None))
        self.agente.conn.commit()
        self.conversacion_id = cursor.lastrowid
        self.proyecto_actual = None
        self._cargar_historial()

    def _cargar_historial(self):
        if not hasattr(self, 'scrollable_frame'):
            return
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        conn = sqlite3.connect('agente_personal.db')
        cursor = conn.cursor()
        cursor.execute('SELECT remitente, contenido FROM mensajes WHERE conversacion_id = ? ORDER BY fecha ASC', (self.conversacion_id,))
        mensajes = cursor.fetchall()
        conn.close()
        for remitente, contenido in mensajes:
            self._insertar_burbuja(remitente, contenido)
        self.root.after(50, lambda: self.canvas.yview_moveto(1.0))  # scroll automático

    def _on_mousewheel(self, event):
        # Soporte para scrollear con la rueda del mouse
        if event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")
        elif event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")

    def _insertar_burbuja(self, remitente, contenido):
        frame = tk.Frame(self.scrollable_frame, bg=DARK_BG)
        if remitente == 'Usuario':
            anchor = 'e'
            color = USER_BUBBLE
            fg = 'white'
            bubble = tk.Label(frame, text=contenido, bg=color, fg=fg, font=FONT, wraplength=500, justify='right', padx=12, pady=8, bd=0, relief='flat')
            bubble.pack(anchor='e', padx=10, pady=4)
            frame.pack(fill='x', anchor='e', padx=(60,10))  # margen izquierdo reducido para usuario
        else:
            anchor = 'w'
            color = AGENT_BUBBLE
            fg = TEXT_COLOR
            bubble = tk.Label(frame, text=contenido, bg=color, fg=fg, font=FONT, wraplength=500, justify='left', padx=12, pady=8, bd=0, relief='flat')
            bubble.pack(anchor='w', padx=10, pady=4)
            frame.pack(fill='x', anchor='w', padx=(10,60))  # margen derecho reducido para agente

    def enviar_mensaje(self, event=None):
        texto = self.entry_msg.get().strip()
        if not texto:
            return
        self._guardar_mensaje('Usuario', texto)
        self.entry_msg.delete(0, tk.END)
        self._cargar_historial()
        # Insertar burbuja del modelo con puntos animados
        self._insertar_burbuja('Agente', '...')
        self.animando = True
        self._animar_puntos()
        threading.Thread(target=self._respuesta_automatica_stream, args=(texto,), daemon=True).start()

    def _respuesta_automatica_stream(self, texto_usuario):
        conn = sqlite3.connect('agente_personal.db')
        cursor = conn.cursor()
        cursor.execute('SELECT remitente, contenido FROM mensajes WHERE conversacion_id = ? ORDER BY fecha ASC', (self.conversacion_id,))
        mensajes = cursor.fetchall()
        historial = []
        for remitente, contenido in mensajes:
            rol = 'user' if remitente == 'Usuario' else 'assistant'
            historial.append({'role': rol, 'content': contenido})
        if not historial or historial[-1]['role'] != 'user':
            historial.append({'role': 'user', 'content': texto_usuario})

        # Insertar burbuja vacía para la respuesta parcial
        self._recibiendo_stream = False
        def actualizar_burbuja(parcial):
            if not self._recibiendo_stream:
                self.animando = False
                self._recibiendo_stream = True
            self.root.after(0, self._actualizar_burbuja_agente, parcial)

        # Usar el helper en modo stream
        from llama_local_helper import obtener_respuesta_llama_stream
        respuesta_final = obtener_respuesta_llama_stream(historial, actualizar_burbuja)
        # Guardar la respuesta final en la base
        cursor.execute('INSERT INTO mensajes (conversacion_id, remitente, tipo, contenido) VALUES (?, ?, ?, ?)',
                       (self.conversacion_id, 'Agente', 'texto', respuesta_final))
        conn.commit()
        conn.close()
        self.respuesta_queue.put(True)

    def _animar_puntos(self):
        if hasattr(self, 'animando') and self.animando:
            burbujas = [w for w in self.scrollable_frame.winfo_children() if isinstance(w, tk.Frame)]
            if burbujas:
                frame = burbujas[-1]
                for widget in frame.winfo_children():
                    if isinstance(widget, tk.Label):
                        actual = widget.cget('text')
                        if actual.endswith('...'):
                            widget.config(text='.')
                        elif actual.endswith('.'):
                            widget.config(text='..')
                        elif actual.endswith('..'):
                            widget.config(text='...')
                        else:
                            widget.config(text='...')
            self.root.after(400, self._animar_puntos)

    def _actualizar_burbuja_agente(self, texto):
        # Actualiza la última burbuja del agente con el texto parcial
        burbujas = [w for w in self.scrollable_frame.winfo_children() if isinstance(w, tk.Frame)]
        if burbujas:
            frame = burbujas[-1]
            for widget in frame.winfo_children():
                if isinstance(widget, tk.Label):
                    widget.config(text=texto)
        # Scroll automático cada vez que se actualiza la burbuja
        self.root.after(10, lambda: self.canvas.yview_moveto(1.0))
    def _on_mousewheel(self, event):
        # Soporte para scrollear con la rueda del mouse (Windows y Linux)
        if hasattr(event, 'delta'):
            # Windows
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        elif event.num == 4:
            # Linux scroll up
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            # Linux scroll down
            self.canvas.yview_scroll(1, "units")
    def _chequear_respuesta(self):
        try:
            if self.respuesta_queue.get_nowait():
                self._cargar_historial()
        except queue.Empty:
            pass
        self.root.after(100, self._chequear_respuesta)
    def _chequear_respuesta(self):
        try:
            if self.respuesta_queue.get_nowait():
                self._cargar_historial()
        except queue.Empty:
            pass
        self.root.after(100, self._chequear_respuesta)

    def dictar_mensaje(self):
        try:
            import speech_recognition as sr
        except ImportError:
            messagebox.showerror('Error', 'Falta instalar speech_recognition. Ejecutá en la terminal: pip install SpeechRecognition')
            return
        def grabar():
            r = sr.Recognizer()
            with sr.Microphone() as source:
                self.btn_microfono.config(state='disabled', bg='#27ae60', fg='white')  # verde
                self.entry_msg.delete(0, tk.END)
                self.entry_msg.insert(0, 'Escuchando...')
                try:
                    audio = r.listen(source, timeout=5)
                    texto = r.recognize_google(audio, language='es-AR')
                    self.entry_msg.delete(0, tk.END)
                    self.entry_msg.insert(0, texto)
                except Exception as e:
                    self.entry_msg.delete(0, tk.END)
                    self.entry_msg.insert(0, '')
                    messagebox.showerror('Error', f'No se pudo transcribir: {e}\n¿Instalaste correctamente el paquete?')
                self.btn_microfono.config(state='normal', bg='#b83a3a', fg='white')  # rojo
        threading.Thread(target=grabar).start()

    def _guardar_mensaje(self, remitente, contenido):
        cursor = self.agente.conn.cursor()
        cursor.execute('INSERT INTO mensajes (conversacion_id, remitente, tipo, contenido) VALUES (?, ?, ?, ?)',
                       (self.conversacion_id, remitente, 'texto', contenido))
        self.agente.conn.commit()

    def borrar_historial(self):
        if not self.conversacion_id:
            return
        conn = sqlite3.connect('agente_personal.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM mensajes WHERE conversacion_id = ?', (self.conversacion_id,))
        conn.commit()
        conn.close()
        self.root.after(0, self._cargar_historial)

if __name__ == '__main__':
    root = tk.Tk()
    app = ChatModernUI(root)
    root.mainloop()
