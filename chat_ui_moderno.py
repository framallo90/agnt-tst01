import functools

def captura_errores_metodo(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            if hasattr(self, '_show_toast_error'):
                self._show_toast_error(f"Error: {e}\nTraceback:\n{tb}")
            else:
                print(f"Error: {e}\nTraceback:\n{tb}")
            return None
    return wrapper
# -*- coding: utf-8 -*-
# --- Constantes de estilo y color ---
DARK_BG = '#23272f'
DARK_PANEL = '#181a20'
DARK_ACCENT = '#2c313c'
TEXT_COLOR = '#e6e6e6'
USER_BUBBLE = '#2556b8'
AGENT_BUBBLE = '#3a8b3a'
FONT = ('Segoe UI', 11)

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
# Theming: use ttkbootstrap if available for a more modern look
try:
    import ttkbootstrap as tb  # type: ignore
except Exception:
    tb = None  # fallback to plain ttk
import queue, threading, sqlite3, traceback

from agente_personal import AgentePersonal
from llama_local_helper import obtener_respuesta_llama_stream, obtener_respuesta_llama

# --- Clase principal de la UI ---
class ChatUI:
    # --- NUEVO: Lectura de archivos ---
    @captura_errores_metodo
    def _leer_archivo(self):
        from tkinter import filedialog
        import os
        import threading
        filetypes = [
            ("Todos", "*.txt *.docx *.xlsx *.csv *.pdf"),
            ("Texto", "*.txt"),
            ("Word", "*.docx"),
            ("Excel", "*.xlsx *.csv"),
            ("PDF", "*.pdf")
        ]
        ruta = filedialog.askopenfilename(title="Selecciona un archivo", filetypes=filetypes)
        if not ruta:
            self._show_toast_error("No se seleccionó ningún archivo.")
            return
        ext = os.path.splitext(ruta)[1].lower()

        def procesar_archivo():
            try:
                contenido = ""
                msg_error = None
                if ext == ".txt":
                    try:
                        with open(ruta, "r", encoding="utf-8") as f:
                            contenido = f.read()
                    except Exception as e:
                        msg_error = f"No se pudo leer el archivo de texto: {e}"
                elif ext == ".docx":
                    try:
                        from docx import Document
                        doc = Document(ruta)
                        contenido = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
                    except Exception as e:
                        msg_error = f"No se pudo leer el archivo Word: {e}"
                elif ext == ".xlsx":
                    try:
                        import pandas as pd
                        df = pd.read_excel(ruta)
                        contenido = df.to_string(index=False)
                    except Exception as e:
                        msg_error = f"No se pudo leer el archivo Excel: {e}"
                elif ext == ".csv":
                    try:
                        import pandas as pd
                        df = pd.read_csv(ruta, encoding="utf-8", engine="python", error_bad_lines=False)
                        contenido = df.to_string(index=False)
                    except Exception as e:
                        msg_error = f"No se pudo leer el archivo CSV: {e}"
                elif ext == ".pdf":
                    try:
                        import pdfplumber
                        with pdfplumber.open(ruta) as pdf:
                            paginas = [page.extract_text() for page in pdf.pages if page.extract_text()]
                            contenido = "\n".join(paginas)
                        if not contenido.strip():
                            msg_error = "El PDF no tiene texto extraíble. Puede estar escaneado o vacío."
                    except Exception as e:
                        msg_error = f"No se pudo leer el archivo PDF: {e}"
                else:
                    self.root.after(0, lambda: self._show_toast_error("Tipo de archivo no soportado."))
                    return
                if msg_error:
                    self.root.after(0, lambda: self._show_toast_error(msg_error))
                    return
                if not contenido.strip():
                    self.root.after(0, lambda: self._show_toast_error("El archivo está vacío o no se pudo extraer texto."))
                    return
                contenido_corto = contenido[:5000]
                prompt = f"Resume el siguiente contenido de archivo para el usuario:\n{contenido_corto}"
                self.root.after(0, lambda: self._insertar_burbuja("Usuario", f"Archivo leído correctamente: {os.path.basename(ruta)}"))
                self.root.after(0, lambda: self._guardar_mensaje("Usuario", f"Archivo leído correctamente: {os.path.basename(ruta)}"))
                self.root.after(0, self._cargar_historial)
                self.root.after(0, lambda: self._insertar_burbuja("Usuario", "Procesando resumen del archivo..."))

                resumen_result = {'done': False, 'resumen': None}
                def modelo_thread():
                    try:
                        resumen_result['resumen'] = obtener_respuesta_llama([
                            {"role": "user", "content": prompt}
                        ])
                    except Exception as e:
                        import traceback
                        tb = traceback.format_exc()
                        resumen_result['resumen'] = f"Error al generar resumen: {e}\nTraceback:\n{tb}"
                        # Mostrar error en la UI si ocurre un crash en el hilo
                        self.root.after(0, lambda: self._show_toast_error(f"Error al generar resumen: {e}\nTraceback:\n{tb}"))
                    finally:
                        resumen_result['done'] = True

                hilo_modelo = threading.Thread(target=modelo_thread)
                hilo_modelo.start()
                hilo_modelo.join(timeout=90)  # Timeout de 90 segundos
                resumen = resumen_result.get('resumen')
                if not resumen_result['done']:
                    # Si el modelo no respondió, usar el fallback demo
                    from llama_local_helper import obtener_respuesta_llama as fallback_llama
                    resumen = fallback_llama([
                        {"role": "user", "content": prompt}
                    ])
                    resumen = f"[Timeout] El modelo no respondió a tiempo. Respuesta alternativa:\n{resumen}"
                if not resumen or not resumen.strip():
                    resumen = "No se pudo generar el resumen del archivo. (El modelo no respondió)"
                self.root.after(0, lambda: self._insertar_burbuja("Usuario", f"Este archivo contiene:\n{resumen}"))
                self.root.after(0, lambda: self._guardar_mensaje("Usuario", f"Este archivo contiene:\n{resumen}"))
                self.root.after(0, self._cargar_historial)
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                self.root.after(0, lambda: self._show_toast_error(f"Error al leer archivo: {e}\nTraceback:\n{tb}"))

        threading.Thread(target=procesar_archivo, daemon=True).start()

    # --- Agregar botón para leer archivo ---
    @captura_errores_metodo
    def _agregar_boton_archivo(self):
        if hasattr(self, 'btn_archivo') and self.btn_archivo:
            self.btn_archivo.pack_forget()
        if self.conversacion_id:
            btn_archivo = self._make_button(self.frame_input, '📄 Leer Archivo', command=self._leer_archivo)
            btn_archivo.pack(side='left', padx=(0, 8))
            self.btn_archivo = btn_archivo
        else:
            self.btn_archivo = None
    # --- Helper para recarga de listboxes ---
    @captura_errores_metodo
    def _reload_listbox(self, listbox, items, seleccionar=None):
        listbox.delete(0, tk.END)
        for item in items:
            listbox.insert(tk.END, item)
        if seleccionar and seleccionar in items:
            idx = items.index(seleccionar)
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(idx)
            listbox.see(idx)
        else:
            listbox.selection_clear(0, tk.END)
    """
    UI del agente personal: proyectos -> chats -> mensajes
    """
    # --- Toast/burbuja de error ---
    @captura_errores_metodo
    def _show_toast_error(self, msg, duration=3500):
        # Crea una burbuja flotante en la esquina inferior derecha de la ventana principal
        if hasattr(self, '_toast_error') and self._toast_error:
            self._toast_error.destroy()
        self._toast_error = tk.Label(
            self.root,
            text=msg,
            bg='#b83a3a',
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            padx=16,
            pady=8,
            bd=2,
            relief='ridge'
        )
        self._toast_error.update_idletasks()
        w = self._toast_error.winfo_reqwidth()
        h = self._toast_error.winfo_reqheight()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        # Si la ventana aún no está visible, usa geometry
        if rw < 10 or rh < 10:
            rw = 720
            rh = 940
        x = rw - w - 24
        y = rh - h - 24
        self._toast_error.place(x=x, y=y)
        self.root.after(duration, lambda: self._toast_error.destroy())
    # --- Toast/burbuja de tip ---
    @captura_errores_metodo
    def _show_toast_tip(self, msg, duration=2500):
        if hasattr(self, '_toast_tip') and self._toast_tip:
            self._toast_tip.destroy()
        self._toast_tip = tk.Label(
            self.root,
            text=msg,
            bg='#2c313c',
            fg='#e6e6e6',
            font=('Segoe UI', 10, 'italic'),
            padx=16,
            pady=8,
            bd=2,
            relief='ridge'
        )
        self._toast_tip.update_idletasks()
        w = self._toast_tip.winfo_reqwidth()
        h = self._toast_tip.winfo_reqheight()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        if rw < 10 or rh < 10:
            rw = 720
            rh = 940
        x = rw - w - 24
        y = rh - h - 24
        self._toast_tip.place(x=x, y=y)
        self.root.after(duration, lambda: self._toast_tip.destroy())
    @captura_errores_metodo
    def __init__(self, root):
        self.root = root
        self.root.title("Agente Personal")
        self.root.geometry("720x940")

        # Estado
        self.agente = None  # Se inicializa en run() para evitar bloquear el render inicial

        self.proyecto_actual = None
        self.proyecto_id = None
        self.conversacion_id = None

        self.respuesta_queue = queue.Queue()
        self.animando = False
        self._recibiendo_stream = False
        # Config: activar/desactivar stream. Por defecto, no-stream para máxima estabilidad.
        self.stream_enabled = False
        # Cancelación de respuestas en curso por conversación
        self._cancelaciones = {}
        # Mapa de chats visibles: índice -> conversacion_id
        self._chat_map = []
        # Grabación de voz (toggle)
        self._grabando = False
        self._grab_stop = None  # type: ignore[assignment]
        self._grab_thread = None  # type: ignore[assignment]
        self._grab_frames = None  # type: ignore
        self._grab_fs = 16000

        # --- INICIALIZACIÓN DE WIDGETS ---
        # --- INICIALIZACIÓN DE WIDGETS ---
        self.frame_main = tk.Frame(self.root, bg=DARK_BG)
        self.frame_main.pack(fill='both', expand=True)
        self.frame_main.pack_propagate(False)
        # Barra lateral con ancho fijo
        self.frame_menu = tk.Frame(self.frame_main, bg=DARK_PANEL, width=260)
        self.frame_menu.pack(side='left', fill='y')
        self.frame_menu.pack_propagate(False)
        # Área de chat flexible
        self.frame_chat = tk.Frame(self.frame_main, bg=DARK_BG)
        self.frame_chat.pack(side='right', fill='both', expand=True)
        self.frame_chat.pack_propagate(True)

        hdr = tk.Frame(self.frame_menu, bg=DARK_PANEL)
        hdr.pack(fill='x', pady=(16, 8))
        tk.Label(hdr, text='Proyectos', bg=DARK_PANEL, fg=TEXT_COLOR,
                 font=('Segoe UI', 13, 'bold')).pack(side='left', padx=(12, 8))
        self.listbox_proyectos = tk.Listbox(
            self.frame_menu, bg=DARK_ACCENT, fg=TEXT_COLOR,
            selectbackground=USER_BUBBLE, selectforeground=TEXT_COLOR,
            relief='flat', font=FONT, highlightthickness=0
        )
        self.listbox_proyectos.pack(fill='both', expand=True, padx=12)
        self.listbox_proyectos.bind('<<ListboxSelect>>', self.seleccionar_proyecto)
        self.listbox_proyectos.bind('<Button-3>', self._mostrar_menu_proyecto)

        self.frame_chats = tk.Frame(self.frame_menu, bg=DARK_PANEL)
        self.frame_chats.pack(fill='both', expand=True, padx=12, pady=(6, 12))
        top_chats = tk.Frame(self.frame_chats, bg=DARK_PANEL)
        top_chats.pack(fill='x')
        tk.Label(top_chats, text='Chats', bg=DARK_PANEL, fg=TEXT_COLOR,
                 font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.listbox_chats = tk.Listbox(
            self.frame_chats, bg=DARK_ACCENT, fg=TEXT_COLOR,
            selectbackground=AGENT_BUBBLE, selectforeground=TEXT_COLOR,
            relief='flat', font=FONT, highlightthickness=0, height=8
        )
        self.listbox_chats.pack(fill='both', expand=True, pady=(6, 6))
        self.listbox_chats.bind('<<ListboxSelect>>', self.seleccionar_chat)
        self.listbox_chats.bind('<Button-3>', self._mostrar_menu_chat)

        # Nuevo recuadro visual para el área de chat
        self.frame_chat_area = tk.Frame(
            self.frame_chat,
            bg=DARK_BG,
            highlightbackground=DARK_ACCENT,
            highlightthickness=1,
            bd=1,
            relief='ridge'
        )
        self.frame_chat_area.pack(side='top', fill='both', expand=True, padx=8, pady=(8, 0))
        self.canvas = tk.Canvas(self.frame_chat_area, bg=DARK_BG, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.frame_chat_area, orient='vertical', command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=DARK_BG)
        self.scrollable_frame.bind(
            '<Configure>',
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        )
        self._scroll_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')
        self.canvas.bind(
            '<Configure>',
            lambda e: self.canvas.itemconfigure(self._scroll_window, width=e.width)
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.scrollbar.pack(side='right', fill='y')

        self.frame_input = tk.Frame(self.frame_chat, bg=DARK_BG)
        self.frame_input.pack(side='bottom', fill='x', padx=8, pady=8)
        self.entry_mensaje = self._make_entry(self.frame_input)
        self.entry_mensaje.pack(side='left', fill='x', expand=True, padx=(0, 8))
        self.entry_mensaje.bind('<Return>', self.enviar_mensaje)
        self._agregar_boton_archivo()
        self.btn_microfono = self._make_button(
            self.frame_input, '🎤', command=self.dictar_mensaje, width=3, primary=True
        )
        self.btn_microfono.pack(side='left', padx=(0, 8))
        self.btn_enviar = self._make_button(
            self.frame_input, 'Enviar', command=self.enviar_mensaje, primary=True
        )
        self.btn_enviar.pack(side='right', padx=(8, 0))
        self.btn_stop = self._make_button(self.frame_input, 'Stop', command=self._cancelar_respuesta, width=6, danger=True)
        self.btn_stop.pack(side='right', padx=(4, 0))
        self.btn_stop.config(state='disabled')
        self.label_puntos = tk.Label(self.frame_input, text="", bg=DARK_BG, fg=AGENT_BUBBLE, font=FONT)
        self.label_puntos.pack(side='left', padx=(8, 0))

        self.btn_renombrar_chat = self._make_button(
            self.frame_chats, '✏️ Renombrar Conversación', command=self.renombrar_chat
        )
        self.btn_eliminar_chat = self._make_button(
            self.frame_chats, '🗑 Eliminar Conversación', command=self.eliminar_chat, danger=True
        )
        self.btn_borrar_hist = self._make_button(
            self.frame_chats, '🗑 Borrar Historial', command=self.borrar_historial, danger=True
        )
        self.btn_renombrar_chat.pack_forget()
        self.btn_eliminar_chat.pack_forget()
        self.btn_borrar_hist.pack_forget()

        self.menu_proyecto = tk.Menu(self.root, tearoff=0)
        self.menu_proyecto.add_command(label='Renombrar Proyecto', command=self.renombrar_proyecto)
        self.menu_proyecto.add_command(label='Eliminar Proyecto', command=self.eliminar_proyecto)
        self.menu_proyecto.add_separator()
        self.menu_proyecto.add_command(label='Nuevo Proyecto', command=self.crear_proyecto)

        self.menu_chat = tk.Menu(self.root, tearoff=0)
        self.menu_chat.add_command(label='Renombrar Conversación', command=self.renombrar_chat)
        self.menu_chat.add_command(label='Eliminar Conversación', command=self.eliminar_chat)
        self.menu_chat.add_command(label='Nuevo Chat', command=self.crear_chat)
        self.menu_chat.add_separator()
        self.menu_chat.add_command(label='Borrar Historial', command=self.borrar_historial)

        self.menu_proyecto_vacio = tk.Menu(self.root, tearoff=0)
        self.menu_proyecto_vacio.add_command(
            label='Seleccioná un proyecto para Renombrar/Eliminar', state='disabled')
        self.menu_proyecto_vacio.add_separator()
        self.menu_proyecto_vacio.add_command(label='Nuevo Proyecto', command=self.crear_proyecto)

        self.menu_chat_vacio_proy = tk.Menu(self.root, tearoff=0)
        self.menu_chat_vacio_proy.add_command(label='Nuevo Chat', command=self.crear_chat)

        self.menu_chat_vacio_sin_proy = tk.Menu(self.root, tearoff=0)
        self.menu_chat_vacio_sin_proy.add_command(label='Seleccioná un proyecto para crear chats', state='disabled')
        self.menu_chat_vacio_sin_proy.add_separator()
        self.menu_chat_vacio_sin_proy.add_command(label='Nuevo Chat', state='disabled')

    # La carga inicial de proyectos e historial se difiere a run() para no bloquear el arranque

    # --- Helper para manejo seguro de errores en UI ---
    @captura_errores_metodo
    def _safe(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            self._set_status(f'Error: {e}', timeout=5000)
            return None

    # ---- Status (pistas) justo encima del input

    # ---------------- Estilos y factories ----------------
    @captura_errores_metodo
    def _init_style(self):
        try:
            if tb:
                # Use a modern dark theme from ttkbootstrap if available
                self.style = tb.Style(theme='darkly')
            else:
                self.style = ttk.Style()
                # Use a neutral modern theme and set colors
                try:
                    self.style.theme_use('clam')
                except Exception:
                    pass
                self.style.configure('TButton', font=FONT)
                self.style.configure('Primary.TButton', font=FONT, foreground='white', background=USER_BUBBLE)
                self.style.map('Primary.TButton', background=[('active', USER_BUBBLE)])
                self.style.configure('Danger.TButton', font=FONT, foreground='white', background='#b83a3a')
                self.style.map('Danger.TButton', background=[('active', '#7a2323')])
                self.style.configure('TEntry', fieldbackground=DARK_ACCENT, foreground=TEXT_COLOR)
        except Exception:
            self.style = ttk.Style()

    @captura_errores_metodo
    def _make_button(self, parent, text, command=None, width=None, primary=False, danger=False):
        if tb:
            bootstyle = 'primary' if primary else ('danger' if danger else 'secondary')
            return tb.Button(parent, text=text, command=command, width=width or 0, bootstyle=bootstyle)
        else:
            style = 'TButton'
            if primary:
                style = 'Primary.TButton'
            elif danger:
                style = 'Danger.TButton'
            btn = ttk.Button(parent, text=text, command=command, style=style)
            if width:
                btn.config(width=width)
            return btn

    @captura_errores_metodo
    def _make_entry(self, parent):
        if tb:
            return tb.Entry(parent, font=FONT)
        else:
            e = ttk.Entry(parent, font=FONT)
            return e

    # ---------------- Menús contextuales ----------------
    @captura_errores_metodo
    def _mostrar_menu_proyecto(self, event):
        has_selection = False
        count = self.listbox_proyectos.size()
        if count > 0:
            idx = self.listbox_proyectos.nearest(event.y)
            bbox = self.listbox_proyectos.bbox(idx)
            if bbox:
                y0, h = bbox[1], bbox[3]
                if y0 <= event.y <= y0 + h:
                    self.listbox_proyectos.selection_clear(0, 'end')
                    self.listbox_proyectos.selection_set(idx)
                    has_selection = True
                    try:
                        self.seleccionar_proyecto()
                    except Exception:
                        pass
        if not has_selection:
            self.listbox_proyectos.selection_clear(0, 'end')

        # Habilitar/Deshabilitar opciones según selección
        state = 'normal' if has_selection else 'disabled'
        try:
            self.menu_proyecto.entryconfig(0, state=state)
            self.menu_proyecto.entryconfig(1, state=state)
        except Exception:
            pass
        menu = self.menu_proyecto if has_selection else self.menu_proyecto_vacio
        if has_selection:
            self._show_toast_tip('Tip: botón derecho para renombrar o eliminar el proyecto seleccionado.')
        else:
            self._show_toast_tip('Tip: no hay proyecto seleccionado. Podés crear uno nuevo desde el menú.')
        menu.tk_popup(event.x_root, event.y_root)

    def _mostrar_menu_chat(self, event):
        has_selection = False
        try:
            count = self.listbox_chats.size()
            if count > 0:
                idx = self.listbox_chats.nearest(event.y)
                bbox = self.listbox_chats.bbox(idx)
                if bbox:
                    y0, h = bbox[1], bbox[3]
                    if y0 <= event.y <= y0 + h:
                        self.listbox_chats.selection_clear(0, 'end')
                        self.listbox_chats.selection_set(idx)
                        has_selection = True
                        try:
                            self.seleccionar_chat()
                        except Exception:
                            pass
                if not has_selection:
                    self.listbox_chats.selection_clear(0, 'end')
            else:
                self.listbox_chats.selection_clear(0, 'end')
        except Exception:
            self.listbox_chats.selection_clear(0, 'end')

        # Habilitar/Deshabilitar opciones del menú de chats
        try:
            state_sel = 'normal' if has_selection else 'disabled'
            # 0: Renombrar Conversación, 1: Eliminar Conversación, 2: Nuevo Chat, 3: sep, 4: Borrar Historial
            self.menu_chat.entryconfig(0, state=state_sel)
            self.menu_chat.entryconfig(1, state=state_sel)
            self.menu_chat.entryconfig(4, state=state_sel)
            # 'Nuevo Chat' solo habilitado si hay proyecto seleccionado
            self.menu_chat.entryconfig(2, state='normal' if self.proyecto_id is not None else 'disabled')
        except Exception:
            pass
        # Elegir menú según haya selección y proyecto actual
        if self.proyecto_id is None:
            # No mostrar ningún menú si no hay proyecto seleccionado
            self._show_toast_tip('Seleccioná un proyecto para poder crear conversaciones.')
            return
        if has_selection:
            menu = self.menu_chat
            self._show_toast_tip('Tip: podés renombrar o eliminar la conversación seleccionada.')
            menu.tk_popup(event.x_root, event.y_root)
        else:
            # Solo mostrar menú vacío si no hay chats, y evitar duplicados
            if self.listbox_chats.size() == 0:
                menu = self.menu_chat_vacio_proy
                self._show_toast_tip('Tip: no hay conversación seleccionada. Creá una nueva desde el menú.')
                menu.tk_popup(event.x_root, event.y_root)

    def _set_status(self, msg: str, timeout: int = 3000):
        # Desactivado: los errores y pistas se muestran solo como toast
        pass

    def _on_mousewheel(self, event):
        if hasattr(event, 'delta') and event.delta:  # Windows
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        else:  # Linux
            if getattr(event, 'num', None) == 4:
                self.canvas.yview_scroll(-1, "units")
            elif getattr(event, 'num', None) == 5:
                self.canvas.yview_scroll(1, "units")

    # ---------------- Proyectos ----------------
    def crear_proyecto(self):
        nombre = simpledialog.askstring('Nuevo Proyecto', 'Nombre del proyecto:')
        if not nombre:
            return
        try:
            with self.agente.lock:
                cur = self.agente.conn.cursor()
                cur.execute("INSERT INTO proyectos (nombre) VALUES (?)", (nombre,))
                self.agente.conn.commit()
            self._cargar_proyectos(seleccionar_nombre=nombre)
        except sqlite3.IntegrityError:
                self._show_toast_error(f'Ya existe un proyecto llamado "{nombre}".')

    def renombrar_proyecto(self):
        if self.proyecto_id is None:
            return
        nuevo = simpledialog.askstring('Renombrar Proyecto', 'Nuevo nombre:')
        if not nuevo:
            return
        try:
            with self.agente.lock:
                cur = self.agente.conn.cursor()
                cur.execute("UPDATE proyectos SET nombre=? WHERE id=?", (nuevo, self.proyecto_id))
                self.agente.conn.commit()
            self._cargar_proyectos(seleccionar_nombre=nuevo)
        except sqlite3.IntegrityError:
            self._show_toast_error(f'Ya existe un proyecto llamado "{nuevo}".')

    def eliminar_proyecto(self):
        sel = self.listbox_proyectos.curselection()
        if not sel:
            return
        nombre = self.listbox_proyectos.get(sel[0])
        with self.agente.lock:
            cur = self.agente.conn.cursor()
            cur.execute('SELECT id FROM proyectos WHERE nombre=?', (nombre,))
            row = cur.fetchone()
        if not row:
            self._show_toast_error('Proyecto no encontrado en la base de datos.')
            self._cargar_proyectos()
            return
        proyecto_id = row[0]
        if not self._safe(messagebox.askyesno, 'Confirmar', f'¿Eliminar el proyecto "{nombre}" y todas sus conversaciones y mensajes?'):
            return
        try:
            with self.agente.lock:
                cur2 = self.agente.conn.cursor()
                convs = cur2.execute('SELECT id FROM conversaciones WHERE proyecto_id=?', (proyecto_id,)).fetchall()
                for (cid,) in convs:
                    ev = self._cancelaciones.get(cid)
                    if ev:
                        ev.set()
                        self._cancelaciones.pop(cid, None)
                self._cancelaciones = {k: v for k, v in self._cancelaciones.items() if k not in [c[0] for c in convs]}
                cur2.execute('BEGIN IMMEDIATE')
                cur2.execute('DELETE FROM proyectos WHERE id=?', (proyecto_id,))
                self.agente.conn.commit()
        except Exception as e:
            self._show_toast_error(f'No se pudo eliminar el proyecto: {e}')
            return
        self.proyecto_actual = None
        self.proyecto_id = None
        self.conversacion_id = None
        self.root.update_idletasks()
        self._safe(messagebox.showinfo, 'Eliminado', f'Proyecto "{nombre}" eliminado correctamente.')
        self._cargar_proyectos()

    def seleccionar_proyecto(self, event=None):
        try:
            sel = self.listbox_proyectos.curselection()
            if not sel:
                return

            idx = sel[0]
            nombre = self.listbox_proyectos.get(idx)
            proyecto_id = None
            with self.agente.lock:
                cur = self.agente.conn.cursor()
                cur.execute('SELECT id FROM proyectos WHERE nombre = ?', (nombre,))
                row = cur.fetchone()
                if row:
                    proyecto_id = row[0]

            if proyecto_id is None:
                self._set_status('Proyecto no encontrado en la base de datos.', 4000)
                return

            self.proyecto_id = proyecto_id
            self.proyecto_actual = nombre
            # Cargar chats y seleccionar el primero si existe
            self._cargar_chats(self.proyecto_id)
            if self._chat_map:
                self.listbox_chats.selection_clear(0, 'end')
                self.listbox_chats.selection_set(0)
                self.listbox_chats.event_generate('<<ListboxSelect>>')
            else:
                self.conversacion_id = None
                self._cargar_historial()
                self.btn_renombrar_chat.pack_forget()
                self.btn_eliminar_chat.pack_forget()
                self.btn_borrar_hist.pack_forget()
        except Exception as e:
            self._set_status(f'Error al seleccionar proyecto: {e}', 5000)

    def _cargar_proyectos(self, seleccionar_nombre: str | None = None):
        try:
            with self.agente.lock:
                cur = self.agente.conn.cursor()
                cur.execute('SELECT nombre FROM proyectos ORDER BY nombre ASC')
                proyectos = [r[0] for r in cur.fetchall()]
        except Exception as e:
            self._set_status(f'Error al cargar proyectos: {e}', 5000)
            proyectos = []
        self._reload_listbox(self.listbox_proyectos, proyectos, seleccionar_nombre)
        if proyectos:
            self.seleccionar_proyecto()
        else:
            self.proyecto_actual = None
            self.proyecto_id = None
            self._reload_listbox(self.listbox_chats, [])
            self.conversacion_id = None
            self._cargar_historial()

    # ---------------- Chats ----------------
    def crear_chat(self):
        if self.proyecto_id is None:
            return
        nombre = simpledialog.askstring('Nuevo Chat', 'Nombre de la conversación:') or 'Conversación'
        with self.agente.lock:
            cur = self.agente.conn.cursor()
            cur.execute('INSERT INTO conversaciones (nombre, proyecto_id) VALUES (?, ?)',
                        (nombre, self.proyecto_id))
            self.agente.conn.commit()
        self._cargar_chats(self.proyecto_id, seleccionar_nombre=nombre)

    def renombrar_chat(self):
        if self.conversacion_id is None:
            return
        nuevo = simpledialog.askstring('Renombrar Conversación', 'Nuevo nombre:')
        if not nuevo:
            return
        with self.agente.lock:
            cur = self.agente.conn.cursor()
            cur.execute('UPDATE conversaciones SET nombre=? WHERE id=?',
                        (nuevo, self.conversacion_id))
            self.agente.conn.commit()
        self._cargar_chats(self.proyecto_id, seleccionar_nombre=nuevo)

    def eliminar_chat(self):
        sel = self.listbox_chats.curselection()
        if not sel:
            self._show_toast_tip('Tip: selecciona una conversación para renombrar o eliminar.')
            return
        idx = sel[0]
        conv_id = self._chat_map[idx]
        nombre = self.listbox_chats.get(idx)
        if not self._safe(messagebox.askyesno, 'Confirmar', f'¿Eliminar la conversación "{nombre}" y su historial?'):
            return
        try:
            with self.agente.lock:
                cur2 = self.agente.conn.cursor()
                ev = self._cancelaciones.get(conv_id)
                if ev:
                    ev.set()
                    self._cancelaciones.pop(conv_id, None)
                self._cancelaciones = {k: v for k, v in self._cancelaciones.items() if k != conv_id}
                cur2.execute('BEGIN IMMEDIATE')
                cur2.execute('DELETE FROM conversaciones WHERE id=?', (conv_id,))
                self.agente.conn.commit()
        except Exception as e:
            self._show_toast_error(f'No se pudo eliminar la conversación: {e}')
            return
        self.conversacion_id = None
        self.root.update_idletasks()
        self._safe(messagebox.showinfo, 'Eliminado', f'Conversación "{nombre}" eliminada correctamente.')
        self._cargar_chats(self.proyecto_id)

    def seleccionar_chat(self, event=None):
        self._agregar_boton_archivo()
        sel = self.listbox_chats.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < 0 or idx >= len(self._chat_map):
            return
        self.conversacion_id = self._chat_map[idx]
        self._cargar_historial()
        self.btn_renombrar_chat.pack(pady=(0, 4), fill='x')
        self.btn_eliminar_chat.pack(pady=(0, 4), fill='x')
        self.btn_borrar_hist.pack(pady=(0, 6), fill='x')

    def _cargar_chats(self, proyecto_id: int, seleccionar_nombre: str | None = None):
        try:
            with self.agente.lock:
                cur = self.agente.conn.cursor()
                cur.execute('SELECT nombre, id FROM conversaciones WHERE proyecto_id=? ORDER BY id ASC', (proyecto_id,))
                rows = cur.fetchall()
        except Exception as e:
            self._set_status(f'Error al cargar conversaciones: {e}', 5000)
            rows = []
        nombres = []
        self._chat_map = []
        for nombre, cid in rows:
            n = nombre or f"Chat #{cid}"
            nombres.append(n)
            self._chat_map.append(cid)
        self._reload_listbox(self.listbox_chats, nombres, seleccionar_nombre)
        # Seleccionar la conversación indicada, si existe
        if seleccionar_nombre and seleccionar_nombre in nombres:
            idx = nombres.index(seleccionar_nombre)
            self.listbox_chats.selection_clear(0, 'end')
            self.listbox_chats.selection_set(idx)
            self.listbox_chats.event_generate('<<ListboxSelect>>')
        elif nombres:
            # Si hay chats pero no se especificó uno, seleccionar el primero
            self.listbox_chats.selection_clear(0, 'end')
            self.listbox_chats.selection_set(0)
            self.listbox_chats.event_generate('<<ListboxSelect>>')
        else:
            # No hay chats: dejar el área de chat en blanco
            self.conversacion_id = None
            self._cargar_historial()

    # (Eliminado método de conversación libre no utilizado)

    # ---------------- Mensajería ----------------
    def _cargar_historial(self):
        if not hasattr(self, 'scrollable_frame'):
            return
        # Limpia todos los frames previos correctamente
        for w in self.scrollable_frame.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass
        self.scrollable_frame.update_idletasks()
        self.canvas.update_idletasks()
        if self.conversacion_id is None:
            self.canvas.yview_moveto(0.0)
            return
        # Inserta solo los mensajes del chat seleccionado
        for remitente, contenido in self.agente.listar_mensajes(self.conversacion_id):
            self._insertar_burbuja(remitente, contenido)
        self.scrollable_frame.update_idletasks()
        self.canvas.update_idletasks()
        self.root.after(50, lambda: self.canvas.yview_moveto(1.0))

    def _insertar_burbuja(self, remitente, contenido):
        frame = tk.Frame(self.scrollable_frame, bg=DARK_BG)
        # Calcular el ancho disponible dinámicamente
        frame.update_idletasks()
        available_width = self.scrollable_frame.winfo_width() or 300
        wrap = max(200, available_width - 100)  # margen para burbuja
        if remitente == 'Usuario':
            bubble = tk.Message(frame, text=contenido, bg=USER_BUBBLE, fg='white',
                               font=FONT, width=wrap, padx=12, pady=8)
            bubble.pack(anchor='e', padx=10, pady=4, fill='x')
            frame.pack(fill='x', anchor='e', padx=(60, 10))
        else:
            bubble = tk.Message(frame, text=contenido, bg=AGENT_BUBBLE, fg=TEXT_COLOR,
                               font=FONT, width=wrap, padx=12, pady=8)
            bubble.pack(anchor='w', padx=10, pady=4, fill='x')
            frame.pack(fill='x', anchor='w', padx=(10, 60))


    def _actualizar_burbuja_agente(self, nuevo_texto):
        """Actualiza el texto de la última burbuja del agente en el chat actual. Si no existe, la crea. Evita duplicados."""
        if self.conversacion_id is None:
            return
        # Buscar la última burbuja del agente
        frames = [frame for frame in reversed(self.scrollable_frame.winfo_children())]
        for frame in frames:
            for widget in frame.winfo_children():
                if isinstance(widget, tk.Message) and widget.cget('bg') == AGENT_BUBBLE:
                    widget.config(text=nuevo_texto)
                    return
        # Si no existe, la crea
        self._insertar_burbuja('Agente', nuevo_texto)

    def _guardar_mensaje(self, remitente, contenido):
        with self.agente.lock:
            # Si no hay conversación seleccionada, crear una acorde al contexto actual
            if self.conversacion_id is None:
                cur = self.agente.conn.cursor()
                if self.proyecto_id is not None:
                    cur.execute('INSERT INTO conversaciones (nombre, proyecto_id) VALUES (?, ?)',
                                ("Conversación", self.proyecto_id))
                else:
                    cur.execute('INSERT INTO conversaciones (nombre, proyecto_id) VALUES (?, ?)',
                                ("Conversación Libre", None))
                self.agente.conn.commit()
                self.conversacion_id = cur.lastrowid
            cur = self.agente.conn.cursor()
            cur.execute('INSERT INTO mensajes (conversacion_id, remitente, tipo, contenido) '
                        'VALUES (?, ?, ?, ?)', (self.conversacion_id, remitente, 'texto', contenido))
            self.agente.conn.commit()

    def enviar_mensaje(self, event=None):
        texto = self.entry_mensaje.get().strip()
        if not texto:
            return
        # Deshabilitar input y botón de enviar
        self.entry_mensaje.config(state='disabled')
        self.btn_enviar.config(state='disabled')
        # Habilitar Stop
        self.btn_stop.config(state='normal')
        # Guardar mensaje del usuario (creará conversación si falta)
        self._guardar_mensaje('Usuario', texto)
        self.entry_mensaje.delete(0, tk.END)
        self._cargar_historial()

        # Burbuja "pensando..."
        self._insertar_burbuja('Agente', '...')
        self.animando = True
        self._animar_puntos()

        # Snapshot para responder sobre la misma conversación aunque el usuario cambie de selección
        conv_id_snapshot = self.conversacion_id
        # Resetear/crear token de cancelación para esta conversación
        ev = threading.Event()
        self._cancelaciones[conv_id_snapshot] = ev
        def reactivar_input():
            self.entry_mensaje.config(state='normal')
            self.btn_enviar.config(state='normal')
            self.btn_stop.config(state='disabled')
        if self.stream_enabled:
            def hilo_stream():
                self._respuesta_streaming(texto, conv_id_snapshot, ev)
                self.root.after(0, reactivar_input)
            threading.Thread(target=hilo_stream, daemon=True).start()
        else:
            def hilo_nostream():
                self._respuesta_nostream(texto, conv_id_snapshot, ev)
                self.root.after(0, reactivar_input)
            threading.Thread(target=hilo_nostream, daemon=True).start()
    
    def _cancelar_respuesta(self):
        # Cancela la respuesta actual del modelo
        conv_id_snapshot = self.conversacion_id
        ev = self._cancelaciones.get(conv_id_snapshot)
        if ev:
            ev.set()
        self.btn_stop.config(state='disabled')

    def _armar_historial(self, conversacion_id: int, texto_usuario: str):
        rows = self.agente.listar_mensajes(conversacion_id)
        historial = [{'role': 'user' if r == 'Usuario' else 'assistant', 'content': c}
                     for r, c in rows]
        if not historial or historial[-1]['role'] != 'user':
            historial.append({'role': 'user', 'content': texto_usuario})
        return historial


    def _respuesta_nostream(self, texto_usuario: str, conversacion_id: int, cancel_event: threading.Event):
        try:
            historial = self._armar_historial(conversacion_id, texto_usuario)
            # Si el modelo soporta callback de cancelación, pásalo aquí
            if hasattr(obtener_respuesta_llama, '__call__') and 'cancel_callback' in obtener_respuesta_llama.__code__.co_varnames:
                def cancel_callback():
                    return cancel_event.is_set()
                respuesta_final = obtener_respuesta_llama(historial, cancel_callback=cancel_callback)
            else:
                respuesta_final = obtener_respuesta_llama(historial)
        except Exception as e:
            respuesta_final = f"[Error del modelo] {e}"
        if cancel_event.is_set():
            self.animando = False
            self.root.after(0, self._actualizar_burbuja_agente, '[Cancelado]')
            return  # conversación eliminada o cancelada
        self.animando = False
        self.root.after(0, self._actualizar_burbuja_agente, respuesta_final)
        try:
            with self.agente.lock:
                if cancel_event.is_set():
                    return
                cur = self.agente.conn.cursor()
                cur.execute('INSERT INTO mensajes (conversacion_id, remitente, tipo, contenido) '
                            'VALUES (?, "Agente", "texto", ?)', (conversacion_id, respuesta_final))
                self.agente.conn.commit()
        except Exception:
            return
        # Limpieza del token de cancelación si sigue siendo el mismo
        self._cancelaciones.pop(conversacion_id, None)
        self.respuesta_queue.put(True)

    def _respuesta_streaming(self, texto_usuario: str, conversacion_id: int, cancel_event: threading.Event):
        historial = self._armar_historial(conversacion_id, texto_usuario)
        self._recibiendo_stream = False

        def actualizar_burbuja(parcial: str):
            if cancel_event.is_set():
                return
            if not self._recibiendo_stream:
                self.animando = False
                self._recibiendo_stream = True
            self.root.after(0, self._actualizar_burbuja_agente, parcial)

        try:
            respuesta_final = obtener_respuesta_llama_stream(historial, actualizar_burbuja)
        except Exception as e:
            respuesta_final = f"[Error de modelo] {e}"
        if cancel_event.is_set():
            return  # conversación eliminada o cancelada
        self.animando = False
        self.root.after(0, self._actualizar_burbuja_agente, respuesta_final)
        try:
            with self.agente.lock:
                if cancel_event.is_set():
                    return
                cur = self.agente.conn.cursor()
                cur.execute('INSERT INTO mensajes (conversacion_id, remitente, tipo, contenido) '
                            'VALUES (?, "Agente", "texto", ?)', (conversacion_id, respuesta_final))
                self.agente.conn.commit()
        except Exception:
            return
        # Limpieza del token de cancelación si sigue siendo el mismo
        self._cancelaciones.pop(conversacion_id, None)
        self.respuesta_queue.put(True)

    # ---------------- Dictado de voz ----------------
    def dictar_mensaje(self):
        """Toggle grabación: click para empezar, click para detener y transcribir + enviar."""
        try:
            import speech_recognition as sr
        except ImportError:
            self._show_toast_error('Necesitás instalar SpeechRecognition para transcribir voz.')
            self._set_status('Falta SpeechRecognition. Instalá: pip install SpeechRecognition', timeout=6000)
            return

        if self._grabando:
            if self._grab_stop:
                self._grab_stop.set()
            th = self._grab_thread
            self._safe(lambda: th and th.join(timeout=2.0))
            self._grabando = False
            self._safe(self.btn_microfono.config, text='🎙')
            self._stop_recording_ui()
            try:
                import numpy as np
                frames = self._grab_frames or []
                if not frames:
                    self._set_status('No se capturó audio.', timeout=3000)
                    return
                data = np.concatenate(frames, axis=0).astype('int16')
                raw = data.tobytes()
                audio = sr.AudioData(raw, self._grab_fs, sample_width=2)
                self._set_status('Procesando…', timeout=3000)
                r = sr.Recognizer()
                try:
                    texto = r.recognize_google(audio, language='es-AR')
                except sr.UnknownValueError:
                    texto = ''
                    self._set_status('No se entendió el audio. Intentá de nuevo.', timeout=4000)
                except Exception as e:
                    self._show_toast_error(f'Transcripción: Error: {e}')
                    texto = ''
                if texto:
                    self.root.after(0, lambda: self._insertar_y_enviar(texto))
            except Exception as e:
                self._show_toast_error(f'Dictado de voz: {e}')
            finally:
                self._grab_thread = None
                self._grab_frames = []
                self._grab_stop = None
            return

        try:
            import sounddevice as sd
            import numpy as np
        except Exception as e:
            self._show_toast_error(f'Audio: No se pudo inicializar sounddevice: {e}\nAsegúrate de que sounddevice esté instalado y el micrófono esté disponible.')
            self._set_status('Error de audio: revisa la configuración del micrófono.', timeout=6000)
            return

        self._grab_stop = threading.Event()
        self._grab_frames = []

        def cb(indata, frames, time_, status):
            try:
                if status:
                    pass
                self._grab_frames.append(indata.copy())
            except Exception:
                pass

        def loop():
            try:
                with sd.InputStream(samplerate=self._grab_fs, channels=1, dtype='int16', callback=cb):
                    self._start_recording_ui()
                    self._set_status('Grabando… click de nuevo para detener.', timeout=0)
                    while self._grab_stop and not self._grab_stop.is_set():
                        sd.sleep(100)
            except Exception as e:
                self._show_toast_error(f'Audio: Error de entrada de audio: {e}')
            finally:
                self._stop_recording_ui()

        self._grab_thread = threading.Thread(target=loop, daemon=True)
        self._grab_thread.start()
        self._grabando = True
        self._safe(self.btn_microfono.config, text='⏹')

    # ---------------- Entrada de texto ----------------
    def _insertar_y_enviar(self, texto):
        if not texto:
            return
        self._guardar_mensaje('Usuario', texto)
        self._cargar_historial()
        self._insertar_burbuja('Usuario', texto)
        # Corrección: el campo de entrada es entry_mensaje
        self.entry_mensaje.delete(0, tk.END)
        self.animando = True
        self._animar_puntos()

        # Snapshot para responder sobre la misma conversación aunque el usuario cambie de selección
        conv_id_snapshot = self.conversacion_id
        # Resetear/crear token de cancelación para esta conversación
        ev = threading.Event()
        self._cancelaciones[conv_id_snapshot] = ev
        if self.stream_enabled:
            threading.Thread(target=self._respuesta_streaming,
                             args=(texto, conv_id_snapshot, ev), daemon=True).start()
        else:
            threading.Thread(target=self._respuesta_nostream,
                             args=(texto, conv_id_snapshot, ev), daemon=True).start()

    def _enfocar_input(self, event=None):
        self.entry_mensaje.focus()
        self.entry_mensaje.select_range(tk.END, tk.END)

    def _animar_puntos(self):
        if not self.animando:
            return
        texto_actual = self.label_puntos.cget("text")
        if texto_actual == "":
            nuevo_texto = "."
        else:
            puntos = texto_actual.count(".")
            if puntos >= 3:
                nuevo_texto = ""
            else:
                nuevo_texto = texto_actual + "."
        self.label_puntos.config(text=nuevo_texto)
        self.root.after(500, self._animar_puntos)

    # ---------------- Startup y carga inicial ----------------
    def _cargar_historial_global(self):
        # Cargar historial de la última conversación activa al iniciar
        try:
            conv_id = None
            with self.agente.lock:
                cur = self.agente.conn.cursor()
                cur.execute('SELECT id, nombre FROM conversaciones WHERE proyecto_id IS NULL ORDER BY id DESC LIMIT 1')
                row = cur.fetchone()
                if row:
                    conv_id = row[0]
            if conv_id is not None:
                # Actualizar estado fuera del lock para evitar deadlocks con listar_mensajes()
                self.conversacion_id = conv_id
                self.proyecto_id = None
                self.proyecto_actual = None
                # Solo cargar historial de la conversación libre sin tocar lista de chats
                self._cargar_historial()
        except Exception:
            pass

    def on_closing(self):
        # Confirmar antes de salir
        if not self._safe(messagebox.askyesno, 'Confirmar salida', '¿Estás seguro que querés salir?'):
            return
        # Cancelar cualquier respuesta en curso
        for ev in self._cancelaciones.values():
            ev.set()
        self.root.destroy()

    def run(self):
        self._init_style()
        self.frame_main.tk_setPalette(background=DARK_BG)
        self.root.configure(bg=DARK_BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        # Status var para pistas
        self.status_var = tk.StringVar()
        status_label = tk.Label(self.frame_main, textvariable=self.status_var, bg=DARK_BG, fg=TEXT_COLOR,
                                font=('Segoe UI', 10))
        status_label.pack(side='bottom', fill='x')
        # Mostrar ventana antes de operaciones de carga para asegurar visibilidad inmediata
        self.root.deiconify()
        self.root.update_idletasks()
        # Inicializar acceso a datos después de mostrar ventana para evitar bloquear el arranque visual
        try:
            self.status_var.set('Inicializando base de datos…')
            # Evitar migración en el hilo principal
            self.agente = AgentePersonal(db_path='agente_personal.db', perform_migration=False)
            try:
                self.agente.conn.execute('PRAGMA foreign_keys = ON')
            except Exception:
                pass
        finally:
            # Limpiar status breve
            self.root.after(500, lambda: self.status_var.set(''))
        # Diferir cargas iniciales para no bloquear el render inicial
        # Sólo cargamos la lista de proyectos; NO auto-cargamos conversaciones libres.
        self.root.after(0, self._cargar_proyectos)
        # Asegurar que el panel de chat quede vacío al inicio (sin proyecto seleccionado)
        self.root.after(0, self._cargar_historial)
        # Enfocar entrada de texto al iniciar
        self.root.after(1000, self._enfocar_input)
        # Bind global para mousewheel (scroll en canvas)
        self.root.bind_all('<MouseWheel>', self._on_mousewheel)
        # (Linux)
        self.root.bind_all('<Button-4>', self._on_mousewheel)
        self.root.bind_all('<Button-5>', self._on_mousewheel)
        self.root.mainloop()

    def borrar_historial(self):
        # Implementación básica: limpia el historial de la conversación actual
        if self.conversacion_id is None:
            self._set_status('No hay conversación seleccionada.', 3000)
            return
        try:
            with self.agente.lock:
                cur = self.agente.conn.cursor()
                cur.execute('DELETE FROM mensajes WHERE conversacion_id=?', (self.conversacion_id,))
                self.agente.conn.commit()
            self._set_status('Historial borrado correctamente.', 3000)
            self._cargar_historial()
        except Exception as e:
            self._set_status(f'Error al borrar historial: {e}', 5000)

if __name__ == '__main__':
    import traceback
    try:
        root = tk.Tk()
        app = ChatUI(root)
        # Volver al flujo original probado: inicialización completa en run()
        app.run()
    except Exception as e:
        print('[FATAL] Error al iniciar la UI:', e)
        traceback.print_exc()
        raise
