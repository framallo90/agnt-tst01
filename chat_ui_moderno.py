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
import queue, threading, sqlite3

from agente_personal import AgentePersonal
from llama_local_helper import obtener_respuesta_llama_stream, obtener_respuesta_llama

# --- Clase principal de la UI ---
class ChatUI:
    """
    UI del agente personal: proyectos -> chats -> mensajes
    """
    def __init__(self, root):
        self.root = root
        self.root.title("Agente Personal")

        # Estado
        self.agente = AgentePersonal(db_path='agente_personal.db')
        # Asegura FK en la misma conexión
        try:
            self.agente.conn.execute('PRAGMA foreign_keys = ON')
        except Exception:
            pass

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

        self._init_style()
        self._build_ui()
        self._cargar_proyectos()
        self._chequear_respuesta()

    # ---------------- UI ----------------
    def _build_ui(self):
        self.root.geometry('900x600')
        self.root.minsize(700, 400)

        # Contenedor principal
        self.frame_main = tk.Frame(self.root, bg=DARK_BG)
        self.frame_main.pack(fill='both', expand=True)

        # ---- Menú lateral (izquierda)
        self.frame_menu = tk.Frame(self.frame_main, bg=DARK_PANEL, width=220)
        self.frame_menu.pack(side='left', fill='y')
        self.frame_menu.pack_propagate(False)

        # Header Proyectos
        hdr = tk.Frame(self.frame_menu, bg=DARK_PANEL)
        hdr.pack(fill='x', pady=(16, 8))
        tk.Label(hdr, text='Proyectos', bg=DARK_PANEL, fg=TEXT_COLOR,
                 font=('Segoe UI', 13, 'bold')).pack(side='left', padx=(12, 8))
    # Botón '+' removido; alta de proyectos desde menú contextual

        # Listbox Proyectos
        self.listbox_proyectos = tk.Listbox(
            self.frame_menu, bg=DARK_ACCENT, fg=TEXT_COLOR,
            selectbackground=USER_BUBBLE, selectforeground=TEXT_COLOR,
            relief='flat', font=FONT, highlightthickness=0
        )
        self.listbox_proyectos.pack(fill='y', expand=True, padx=12)
        self.listbox_proyectos.bind('<<ListboxSelect>>', self.seleccionar_proyecto)
        self.listbox_proyectos.bind('<Button-3>', self._mostrar_menu_proyecto)

        # (Botones de proyecto removidos; usar menú contextual)

        # Panel de chats por proyecto
        self.frame_chats = tk.Frame(self.frame_menu, bg=DARK_PANEL)
        self.frame_chats.pack(fill='x', padx=12, pady=(6, 12))

        top_chats = tk.Frame(self.frame_chats, bg=DARK_PANEL)
        top_chats.pack(fill='x')
        tk.Label(top_chats, text='Chats', bg=DARK_PANEL, fg=TEXT_COLOR,
                 font=('Segoe UI', 12, 'bold')).pack(side='left')
        # El botón '+' para crear chats ya no se usa; se crea mediante el menú contextual.

        self.listbox_chats = tk.Listbox(
            self.frame_chats, bg=DARK_ACCENT, fg=TEXT_COLOR,
            selectbackground=AGENT_BUBBLE, selectforeground=TEXT_COLOR,
            relief='flat', font=FONT, highlightthickness=0, height=8
        )
        self.listbox_chats.pack(fill='x', pady=(6, 6))
        self.listbox_chats.bind('<<ListboxSelect>>', self.seleccionar_chat)
        self.listbox_chats.bind('<Button-3>', self._mostrar_menu_chat)

        # Acciones de chat
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

        # Menús contextuales
        self.menu_proyecto = tk.Menu(self.root, tearoff=0)
        self.menu_proyecto.add_command(label='Renombrar Proyecto', command=self.renombrar_proyecto)
        self.menu_proyecto.add_command(label='Eliminar Proyecto', command=self.eliminar_proyecto)
        self.menu_proyecto.add_separator()
        # Crear nuevos proyectos desde el menú contextual de Proyectos
        self.menu_proyecto.add_command(label='Nuevo Proyecto', command=self.crear_proyecto)

        self.menu_chat = tk.Menu(self.root, tearoff=0)
        self.menu_chat.add_command(label='Renombrar Conversación', command=self.renombrar_chat)
        self.menu_chat.add_command(label='Eliminar Conversación', command=self.eliminar_chat)
        # Añadimos la opción de crear nuevo chat al menú contextual de chats
        self.menu_chat.add_command(label='Nuevo Chat', command=self.crear_chat)
        self.menu_chat.add_separator()
        self.menu_chat.add_command(label='Borrar Historial', command=self.borrar_historial)

        # Menús alternativos con pista cuando no hay selección
        self.menu_proyecto_vacio = tk.Menu(self.root, tearoff=0)
        self.menu_proyecto_vacio.add_command(
            label='Seleccioná un proyecto para Renombrar/Eliminar', state='disabled')
        self.menu_proyecto_vacio.add_separator()
        self.menu_proyecto_vacio.add_command(label='Nuevo Proyecto', command=self.crear_proyecto)

        self.menu_chat_vacio_proy = tk.Menu(self.root, tearoff=0)
        self.menu_chat_vacio_proy.add_command(
            label='Seleccioná un chat o creá uno nuevo', state='disabled')
        self.menu_chat_vacio_proy.add_separator()
        self.menu_chat_vacio_proy.add_command(label='Nuevo Chat', command=self.crear_chat)

        self.menu_chat_vacio_sin_proy = tk.Menu(self.root, tearoff=0)
        self.menu_chat_vacio_sin_proy.add_command(
            label='Seleccioná un proyecto para crear chats', state='disabled')
        self.menu_chat_vacio_sin_proy.add_separator()
        self.menu_chat_vacio_sin_proy.add_command(label='Nuevo Chat', state='disabled')

        # ---- Área de chat (derecha)
        self.frame_chat = tk.Frame(self.frame_main, bg=DARK_BG)
        self.frame_chat.pack(side='right', fill='both', expand=True)

        self.canvas = tk.Canvas(self.frame_chat, bg=DARK_BG, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.frame_chat, orient='vertical', command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=DARK_BG)
        self.scrollable_frame.bind('<Configure>',
                                   lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.scrollbar.pack(side='right', fill='y')

        # Soporte scroll con rueda
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)  # Windows
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)    # Linux up
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)    # Linux down

        # ---- Status (pistas) justo encima del input
        self.status_var = tk.StringVar(value='')
        self.frame_status = tk.Frame(self.root, bg=DARK_PANEL)
        self.frame_status.pack(side='bottom', fill='x')
        self.lbl_status = tk.Label(self.frame_status, textvariable=self.status_var,
                                   bg=DARK_PANEL, fg='#9aa0a6', font=('Segoe UI', 9))
        self.lbl_status.pack(side='left', padx=(20, 5), pady=(2, 2))

        # ---- Input abajo
        self.frame_input = tk.Frame(self.root, bg=DARK_PANEL)
        self.frame_input.pack(side='bottom', fill='x')
        self.entry_msg = self._make_entry(self.frame_input)
        # Para que los botones a la derecha no se escondan al achicar, los anclamos a la derecha
        self.btn_enviar = self._make_button(self.frame_input, 'Enviar', command=self.enviar_mensaje, primary=True)
        # Mic button style similar to modern assistants
        self.btn_microfono = self._make_button(self.frame_input, '�', command=self.dictar_mensaje)
        try:
            # Slightly narrower to look like an icon button
            self.btn_microfono.config(width=3)
        except Exception:
            pass
        # Empaquetar primero los botones a la derecha, luego la entrada expandible a la izquierda
        self.btn_enviar.pack(side='right', padx=(5, 20), pady=12)
        self.btn_microfono.pack(side='right', padx=5, pady=12)
        self.entry_msg.pack(side='left', padx=(20, 5), pady=12, fill='x', expand=True)
        self.entry_msg.bind('<Return>', self.enviar_mensaje)

    # ---------------- Estilos y factories ----------------
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

    def _make_entry(self, parent):
        if tb:
            return tb.Entry(parent, font=FONT)
        else:
            e = ttk.Entry(parent, font=FONT)
            return e

    # ---------------- Menús contextuales ----------------
    def _mostrar_menu_proyecto(self, event):
        has_selection = False
        try:
            count = self.listbox_proyectos.size()
            if count > 0:
                idx = self.listbox_proyectos.nearest(event.y)
                # Validar si el click cayó dentro del bbox del item
                bbox = self.listbox_proyectos.bbox(idx)
                if bbox:
                    y0, h = bbox[1], bbox[3]
                    if y0 <= event.y <= y0 + h:
                        self.listbox_proyectos.selection_clear(0, 'end')
                        self.listbox_proyectos.selection_set(idx)
                        has_selection = True
                        # Actualizar estado interno manualmente
                        try:
                            self.seleccionar_proyecto()
                        except Exception:
                            pass
                if not has_selection:
                    # Click fuera de items: limpiar selección
                    self.listbox_proyectos.selection_clear(0, 'end')
            else:
                self.listbox_proyectos.selection_clear(0, 'end')
        except Exception:
            self.listbox_proyectos.selection_clear(0, 'end')

        # Habilitar/Deshabilitar opciones según selección
        try:
            state = 'normal' if has_selection else 'disabled'
            # 0: Renombrar Proyecto, 1: Eliminar Proyecto
            self.menu_proyecto.entryconfig(0, state=state)
            self.menu_proyecto.entryconfig(1, state=state)
            # 'Nuevo Proyecto' siempre habilitado
        except Exception:
            pass
        # Elegir menú según haya selección o no
        menu = self.menu_proyecto if has_selection else self.menu_proyecto_vacio
        # Pista en status
        if has_selection:
            self._set_status('Tip: botón derecho para renombrar o eliminar el proyecto seleccionado.')
        else:
            self._set_status('Tip: no hay proyecto seleccionado. Podés crear uno nuevo desde el menú.')
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
        if has_selection:
            menu = self.menu_chat
            self._set_status('Tip: podés renombrar o eliminar la conversación seleccionada.')
        else:
            if self.proyecto_id is not None:
                menu = self.menu_chat_vacio_proy
                self._set_status('Tip: no hay conversación seleccionada. Creá una nueva desde el menú.')
            else:
                menu = self.menu_chat_vacio_sin_proy
                self._set_status('Tip: seleccioná un proyecto para poder crear conversaciones.')
        menu.tk_popup(event.x_root, event.y_root)

    def _set_status(self, msg: str, timeout: int = 3000):
        try:
            self.status_var.set(msg)
            if timeout:
                self.root.after(timeout, lambda: self.status_var.set(''))
        except Exception:
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
            messagebox.showerror('Error', f'Ya existe un proyecto llamado "{nombre}".')

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
            messagebox.showerror('Error', f'Ya existe un proyecto llamado "{nuevo}".')

    def eliminar_proyecto(self):
        # Eliminación con transacción y confianza en ON DELETE CASCADE
        sel = self.listbox_proyectos.curselection()
        if not sel:
            # nothing selected
            return
        nombre = self.listbox_proyectos.get(sel[0])
        with self.agente.lock:
            cur = self.agente.conn.cursor()
            cur.execute('SELECT id FROM proyectos WHERE nombre=?', (nombre,))
            row = cur.fetchone()
        if not row:
            messagebox.showerror('Error', 'Proyecto no encontrado en la base de datos.')
            self._cargar_proyectos()
            return
        proyecto_id = row[0]
        if not messagebox.askyesno('Confirmar', f'¿Eliminar el proyecto "{nombre}" y todas sus conversaciones y mensajes?'):
            return
        try:
            with self.agente.lock:
                cur2 = self.agente.conn.cursor()
                # Cancelar respuestas en curso de todas las conversaciones del proyecto
                convs = cur2.execute('SELECT id FROM conversaciones WHERE proyecto_id=?', (proyecto_id,)).fetchall()
                for (cid,) in convs:
                    ev = self._cancelaciones.get(cid)
                    if ev:
                        ev.set()
                        # quitar del mapa para evitar fugas
                        self._cancelaciones.pop(cid, None)
                cur2.execute('BEGIN IMMEDIATE')
                # Borrar sólo el proyecto; la cascada se encarga del resto
                cur2.execute('DELETE FROM proyectos WHERE id=?', (proyecto_id,))
                self.agente.conn.commit()
        except Exception as e:
            messagebox.showerror('Error', f'No se pudo eliminar el proyecto: {e}')
            return

        # Immediate UI update: remove the project from the listbox so user sees change at once
        try:
            sel_idx = sel[0]
            self.listbox_proyectos.delete(sel_idx)
        except Exception:
            # if deletion from listbox fails, just reload all projects
            pass

        # Reset internal state and refresh UI components
        self.proyecto_actual = None
        self.proyecto_id = None
        self.conversacion_id = None
        self.root.update_idletasks()
        messagebox.showinfo('Eliminado', f'Proyecto "{nombre}" eliminado correctamente.')
        # Ensure full reload to keep consistency
        self._cargar_proyectos()

    def seleccionar_proyecto(self, event=None):
        sel = self.listbox_proyectos.curselection()
        if not sel:
            # No crear ni borrar conversaciones al deseleccionar proyecto.
            # Solo ocultar acciones de proyecto y dejar el chat actual como está.
            self.proyecto_actual = None
            self.proyecto_id = None
            # (Botones de proyecto removidos)
            self.btn_renombrar_chat.pack_forget()
            self.btn_eliminar_chat.pack_forget()
            self.btn_borrar_hist.pack_forget()
            return

        nombre = self.listbox_proyectos.get(sel[0])
        cur = self.agente.conn.cursor()
        cur.execute('SELECT id FROM proyectos WHERE nombre = ?', (nombre,))
        row = cur.fetchone()
        if row:
            self.proyecto_id = row[0]
            self.proyecto_actual = nombre
            self._cargar_chats(self.proyecto_id)
            # (Botones de proyecto removidos)

    def _cargar_proyectos(self, seleccionar_nombre: str | None = None):
        self.listbox_proyectos.delete(0, tk.END)
        cur = self.agente.conn.cursor()
        cur.execute('SELECT nombre FROM proyectos ORDER BY nombre ASC')
        proyectos = [r[0] for r in cur.fetchall()]
        for p in proyectos:
            self.listbox_proyectos.insert(tk.END, p)

        if proyectos:
            idx = 0
            if seleccionar_nombre and seleccionar_nombre in proyectos:
                idx = proyectos.index(seleccionar_nombre)
            self.listbox_proyectos.selection_clear(0, tk.END)
            self.listbox_proyectos.selection_set(idx)
            self.seleccionar_proyecto()
        else:
            # Sin proyectos: no crear conversaciones libres automáticamente.
            self.proyecto_actual = None
            self.proyecto_id = None
            self.listbox_chats.delete(0, tk.END)
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
        # Eliminación simple con cascada de mensajes
        sel = self.listbox_chats.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < 0 or idx >= len(self._chat_map):
            return
        conv_id = self._chat_map[idx]
        nombre = self.listbox_chats.get(idx)
        if not messagebox.askyesno('Confirmar', f'¿Eliminar la conversación "{nombre}" y su historial?'):
            return
        try:
            with self.agente.lock:
                cur2 = self.agente.conn.cursor()
                # Cancelar respuesta en curso asociada a esta conversación
                ev = self._cancelaciones.get(conv_id)
                if ev:
                    ev.set()
                    self._cancelaciones.pop(conv_id, None)
                cur2.execute('BEGIN IMMEDIATE')
                cur2.execute('DELETE FROM conversaciones WHERE id=?', (conv_id,))
                self.agente.conn.commit()
        except Exception as e:
            messagebox.showerror('Error', f'No se pudo eliminar la conversación: {e}')
            return

        # Immediate UI update: remove chat entry from listbox so it's not visible anymore
        try:
            self.listbox_chats.delete(idx)
            try:
                del self._chat_map[idx]
            except Exception:
                pass
        except Exception:
            pass

        self.conversacion_id = None
        self.root.update_idletasks()
        messagebox.showinfo('Eliminado', f'Conversación "{nombre}" eliminada correctamente.')
        self._cargar_chats(self.proyecto_id)

    def seleccionar_chat(self, event=None):
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
        self.listbox_chats.delete(0, tk.END)
        self._chat_map = []
        cur = self.agente.conn.cursor()
        cur.execute('SELECT nombre, id FROM conversaciones WHERE proyecto_id=? ORDER BY id ASC',
                    (proyecto_id,))
        rows = cur.fetchall()
        nombres = []
        for nombre, cid in rows:
            n = nombre or f"Chat #{cid}"
            nombres.append(n)
            self._chat_map.append(cid)
            self.listbox_chats.insert(tk.END, n)

        if nombres:
            idx = 0
            if seleccionar_nombre and seleccionar_nombre in nombres:
                idx = nombres.index(seleccionar_nombre)
            self.listbox_chats.selection_clear(0, tk.END)
            self.listbox_chats.selection_set(idx)
            self.seleccionar_chat()
        else:
            # No crear chats automáticamente; quedar en estado sin conversación
            self.conversacion_id = None
            self._cargar_historial()

    # (Eliminado método de conversación libre no utilizado)

    # ---------------- Mensajería ----------------
    def _cargar_historial(self):
        if not hasattr(self, 'scrollable_frame'):
            return
        for w in self.scrollable_frame.winfo_children():
            w.destroy()
        if self.conversacion_id is None:
            return

        cur = self.agente.conn.cursor()
        cur.execute('SELECT remitente, contenido FROM mensajes WHERE conversacion_id = ? '
                    'ORDER BY datetime(fecha) ASC, id ASC', (self.conversacion_id,))
        for remitente, contenido in cur.fetchall():
            self._insertar_burbuja(remitente, contenido)

        self.root.after(50, lambda: self.canvas.yview_moveto(1.0))

    def _insertar_burbuja(self, remitente, contenido):
        frame = tk.Frame(self.scrollable_frame, bg=DARK_BG)
        if remitente == 'Usuario':
            bubble = tk.Label(frame, text=contenido, bg=USER_BUBBLE, fg='white',
                              font=FONT, wraplength=600, justify='right',
                              padx=12, pady=8, bd=0, relief='flat')
            bubble.pack(anchor='e', padx=10, pady=4)
            frame.pack(fill='x', anchor='e', padx=(60, 10))
        else:
            bubble = tk.Label(frame, text=contenido, bg=AGENT_BUBBLE, fg=TEXT_COLOR,
                              font=FONT, wraplength=600, justify='left',
                              padx=12, pady=8, bd=0, relief='flat')
            bubble.pack(anchor='w', padx=10, pady=4)
            frame.pack(fill='x', anchor='w', padx=(10, 60))

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
        texto = self.entry_msg.get().strip()
        if not texto:
            return
        # Guardar mensaje del usuario (creará conversación si falta)
        self._guardar_mensaje('Usuario', texto)
        self.entry_msg.delete(0, tk.END)
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
        if self.stream_enabled:
            threading.Thread(target=self._respuesta_streaming,
                             args=(texto, conv_id_snapshot, ev), daemon=True).start()
        else:
            threading.Thread(target=self._respuesta_nostream,
                             args=(texto, conv_id_snapshot, ev), daemon=True).start()

    def _armar_historial(self, conversacion_id: int, texto_usuario: str):
        with self.agente.lock:
            cur = self.agente.conn.cursor()
            cur.execute('SELECT remitente, contenido FROM mensajes WHERE conversacion_id = ? '
                        'ORDER BY datetime(fecha) ASC, id ASC', (conversacion_id,))
            rows = cur.fetchall()
        historial = [{'role': 'user' if r == 'Usuario' else 'assistant', 'content': c}
                     for r, c in rows]
        if not historial or historial[-1]['role'] != 'user':
            historial.append({'role': 'user', 'content': texto_usuario})
        return historial

    def _respuesta_nostream(self, texto_usuario: str, conversacion_id: int, cancel_event: threading.Event):
        try:
            historial = self._armar_historial(conversacion_id, texto_usuario)
            respuesta_final = obtener_respuesta_llama(historial)
        except Exception as e:
            respuesta_final = f"[Error del modelo] {e}"
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
            try:
                respuesta_final = obtener_respuesta_llama(historial)
            except Exception:
                respuesta_final = f"[Error del modelo] {e}"
            self.root.after(0, self._actualizar_burbuja_agente, respuesta_final)

        if cancel_event.is_set():
            return
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
        self._cancelaciones.pop(conversacion_id, None)
        self.respuesta_queue.put(True)

    def _animar_puntos(self):
        if self.animando:
            frames = [w for w in self.scrollable_frame.winfo_children() if isinstance(w, tk.Frame)]
            if frames:
                frame = frames[-1]
                for widget in frame.winfo_children():
                    if isinstance(widget, tk.Label):
                        t = widget.cget('text')
                        widget.config(text='.' if t.endswith('...') else '..' if t.endswith('.') else
                                      '...' if t.endswith('..') else '...')
            self.root.after(400, self._animar_puntos)

    def _actualizar_burbuja_agente(self, texto: str):
        frames = [w for w in self.scrollable_frame.winfo_children() if isinstance(w, tk.Frame)]
        if not frames:
            return
        frame = frames[-1]
        for widget in frame.winfo_children():
            if isinstance(widget, tk.Label):
                widget.config(text=texto)
        self.root.after(10, lambda: self.canvas.yview_moveto(1.0))

    def _chequear_respuesta(self):
        try:
            if self.respuesta_queue.get_nowait():
                self.animando = False
                self._cargar_historial()
        except queue.Empty:
            pass
        self.root.after(100, self._chequear_respuesta)

    # ---------------- Utilidades varias ----------------
    def dictar_mensaje(self):
        """Captura voz y transcribe usando speech_recognition (Google)."""
        try:
            import speech_recognition as sr
        except ImportError:
            self._set_status('Falta SpeechRecognition. Instalá: pip install SpeechRecognition pyaudio', timeout=6000)
            msg = (
                'Para usar dictado de voz:\n'
                '- pip install SpeechRecognition\n'
                '- En Windows, también PyAudio (pip install pipwin && pipwin install pyaudio)'
            )
            messagebox.showerror('Falta dependencia', msg)
            return

        def grabar():
            r = sr.Recognizer()
            try:
                # Primer intento: Microphone (requiere PyAudio)
                try:
                    src = sr.Microphone()
                    use_pyaudio = True
                except Exception:
                    src = None
                    use_pyaudio = False

                try:
                    self.btn_microfono.config(state='disabled')
                except Exception:
                    pass
                self.entry_msg.delete(0, tk.END)
                self.entry_msg.insert(0, 'Escuchando…')
                self._set_status('Grabando… hablá cerca del micrófono (hasta 8s).', timeout=8000)

                if use_pyaudio and src is not None:
                    with src as source:
                        audio = r.listen(source, timeout=5, phrase_time_limit=8)
                else:
                    # Fallback: sounddevice (sin PyAudio)
                    try:
                        import sounddevice as sd
                        import numpy as np
                    except Exception as e:
                        raise RuntimeError('No hay PyAudio ni sounddevice disponible para capturar audio.') from e
                    fs = 16000
                    seconds = 8
                    try:
                        self._set_status('Grabando (fallback)…', timeout=seconds * 1000)
                        data = sd.rec(int(seconds * fs), samplerate=fs, channels=1, dtype='int16')
                        sd.wait()
                        raw = data.tobytes()
                        audio = sr.AudioData(raw, fs, sample_width=2)
                    except Exception as e:
                        raise RuntimeError(f'Error de captura (fallback): {e}')

                # Reconocer
                self._set_status('Procesando…', timeout=3000)
                try:
                    texto = r.recognize_google(audio, language='es-AR')
                except sr.UnknownValueError:
                    texto = ''
                    self._set_status('No se entendió el audio. Intentá de nuevo.', timeout=4000)
                except Exception as e:
                    raise RuntimeError(f'Error de transcripción: {e}')

                self.entry_msg.delete(0, tk.END)
                if texto:
                    self.entry_msg.insert(0, texto)
                else:
                    self.entry_msg.insert(0, '')

            except sr.WaitTimeoutError:
                self.entry_msg.delete(0, tk.END)
                self._set_status('No se detectó voz. Intentá de nuevo.', timeout=4000)
            except Exception as err:
                self.entry_msg.delete(0, tk.END)
                messagebox.showerror('Dictado de voz', str(err))
            finally:
                try:
                    self.btn_microfono.config(state='normal')
                except Exception:
                    pass

        threading.Thread(target=grabar, daemon=True).start()

    def borrar_historial(self):
        if not self.conversacion_id:
            return
        if not messagebox.askyesno('Confirmar', '¿Borrar todos los mensajes de esta conversación?'):
            return
        cur = self.agente.conn.cursor()
        cur.execute('DELETE FROM mensajes WHERE conversacion_id = ?', (self.conversacion_id,))
        self.agente.conn.commit()
        self._cargar_historial()


if __name__ == '__main__':
    root = tk.Tk()
    app = ChatUI(root)
    root.mainloop()
