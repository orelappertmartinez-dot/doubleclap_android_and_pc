import argparse
import json
import os
import sys
import time

import numpy as np
import sounddevice as sd
import tkinter as tk
from tkinter import filedialog, messagebox

# --- Runtime config ---
DEFAULT_THRESHOLD = 30.0
MIN_INTERVAL = 0.1
MAX_INTERVAL = 1.0
DEFAULT_APPS = []
APP_DIR_NAME = "ClapTrigger"
STARTUP_NAME = "clap-trigger-startup.vbs"

# --- Desktop theme ---
WINDOW_BG = "#070d15"
CARD_BG = "#101827"
CARD_ALT_BG = "#141e30"
CARD_BORDER = "#22314a"
PRIMARY_COLOR = "#2f7bff"
PRIMARY_HOVER = "#47a8ff"
SECONDARY_COLOR = "#2d374a"
SECONDARY_HOVER = "#3a4860"
PILL_BG = "#0d1523"
GLOW_RING_ONE = "#0f2847"
GLOW_RING_TWO = "#153a6b"
GLOW_RING_THREE = "#1f69d8"
TIP_BG = "#0d1624"
TEXT_COLOR = "#eef4ff"
MUTED_TEXT = "#9aaac4"
SUCCESS_TEXT = "#7fe0a8"
ERROR_TEXT = "#ff9393"
ENTRY_BG = "#182334"
ROW_SELECTED = "#16396f"
ICON_BG = "#1f4fa6"


def clamp_threshold(value):
    return max(0.0, min(90.0, value))


def is_frozen_app():
    return getattr(sys, "frozen", False)


def get_runtime_dir():
    if is_frozen_app():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_config_file():
    if is_frozen_app():
        base_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
        config_dir = os.path.join(base_dir, APP_DIR_NAME)
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "clap-config.json")
    return os.path.join(get_runtime_dir(), "clap-config.json")


CONFIG_FILE = get_config_file()


def parse_args():
    parser = argparse.ArgumentParser(description="Clap trigger para abrir aplicaciones con dos palmadas.")
    parser.add_argument(
        "-t",
        "--threshold",
        type=float,
        help="Umbral en dB. Valores mas bajos hacen la deteccion mas sensible.",
    )
    parser.add_argument(
        "--configure",
        action="store_true",
        help="Abrir el configurador con interfaz grafica.",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Eliminar el arranque automatico de Windows.",
    )
    parser.add_argument(
        "--background",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"threshold": DEFAULT_THRESHOLD, "apps": DEFAULT_APPS.copy()}

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        threshold = clamp_threshold(float(data.get("threshold", DEFAULT_THRESHOLD)))
        apps = data.get("apps", DEFAULT_APPS.copy())
        if not isinstance(apps, list):
            apps = DEFAULT_APPS.copy()
        return {"threshold": threshold, "apps": apps}
    except (ValueError, OSError, json.JSONDecodeError):
        return {"threshold": DEFAULT_THRESHOLD, "apps": DEFAULT_APPS.copy()}


def save_config(config):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False


def get_startup_folder():
    return os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "Startup",
    )


def get_pythonw_executable():
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        candidate = exe[:-4] + "w.exe"
        if os.path.exists(candidate):
            return candidate
    return exe


def get_launch_command(background=False):
    if is_frozen_app():
        command = [os.path.abspath(sys.executable)]
    else:
        command = [get_pythonw_executable(), os.path.abspath(__file__)]

    if background:
        command.append("--background")
    return command


def get_startup_script_path():
    return os.path.join(get_startup_folder(), STARTUP_NAME)


def install_startup():
    startup_folder = get_startup_folder()
    if not startup_folder or not os.path.isdir(startup_folder):
        return False

    vbs_path = get_startup_script_path()
    command_parts = get_launch_command(background=True)
    quoted_parts = [f'"""" & "{part}" & """"' for part in command_parts]
    command_expr = ' & " " & '.join(quoted_parts)

    content = 'Set WshShell = CreateObject("WScript.Shell")\n'
    content += f'cmd = {command_expr}\n'
    content += 'WshShell.Run cmd, 0, false\n'

    if os.path.exists(vbs_path):
        return True

    try:
        with open(vbs_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return True
    except OSError:
        return False


def uninstall_startup():
    try:
        path = get_startup_script_path()
        if os.path.exists(path):
            os.remove(path)
            return True
    except OSError:
        pass
    return False


def startup_installed():
    return os.path.exists(get_startup_script_path())


def launch_apps(apps):
    print("\n" + "=" * 40)
    print("  DOBLE PALMADA detectada. Abriendo aplicaciones...")
    print("=" * 40)

    for app in apps:
        if os.path.exists(app):
            os.startfile(app)
            print(f"  -> Abriendo: {app}")
            time.sleep(1)
        else:
            print(f"  ! No existe: {app}")


def listen_forever(threshold, apps):
    print(f"Escuchando... (Umbral: {threshold} dB)")
    if not apps:
        print("No hay aplicaciones configuradas. Abre el configurador para anadirlas.")
        return

    last_clap_time = 0

    def callback(indata, frames, time_info, status):
        nonlocal last_clap_time
        volume = np.linalg.norm(indata) * 10
        db = 20 * np.log10(volume) if volume > 0 else 0

        if db > threshold:
            now = time.time()
            if MIN_INTERVAL < (now - last_clap_time) < MAX_INTERVAL:
                launch_apps(apps)
                last_clap_time = 0
            else:
                last_clap_time = now
                print(f"[*] Palmada 1 detectada ({db:.1f} dB)")

    try:
        with sd.InputStream(callback=callback):
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nDetenido por el usuario.")


def center_window(root, width, height):
    root.update_idletasks()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    pos_x = max(0, (screen_width - width) // 2)
    pos_y = max(20, (screen_height - height) // 2 - 20)
    root.geometry(f"{width}x{height}+{pos_x}+{pos_y}")


def apply_fade_in(root):
    try:
        root.attributes("-alpha", 0.0)
    except tk.TclError:
        return

    def fade(step=0):
        alpha = min(1.0, step / 12.0)
        try:
            root.attributes("-alpha", alpha)
        except tk.TclError:
            return
        if alpha < 1.0:
            root.after(18, fade, step + 1)

    root.after(20, fade)


def create_card(parent, bg=CARD_BG, padx=16, pady=16):
    return tk.Frame(
        parent,
        bg=bg,
        highlightthickness=1,
        highlightbackground=CARD_BORDER,
        highlightcolor=CARD_BORDER,
        bd=0,
        padx=padx,
        pady=pady,
    )


def style_button(button, bg_color, hover_color):
    button.configure(
        bg=bg_color,
        fg=TEXT_COLOR,
        activebackground=hover_color,
        activeforeground=TEXT_COLOR,
        relief=tk.FLAT,
        bd=0,
        highlightthickness=0,
        padx=14,
        pady=10,
        cursor="hand2",
        font=("Segoe UI", 11, "bold"),
    )
    button.bind("<Enter>", lambda _event: button.configure(bg=hover_color))
    button.bind("<Leave>", lambda _event: button.configure(bg=bg_color))


def create_button(parent, text, command, primary=True):
    button = tk.Button(parent, text=text, command=command)
    style_button(
        button,
        PRIMARY_COLOR if primary else SECONDARY_COLOR,
        PRIMARY_HOVER if primary else SECONDARY_HOVER,
    )
    return button


def style_entry(entry):
    entry.configure(
        bg=ENTRY_BG,
        fg=TEXT_COLOR,
        insertbackground=TEXT_COLOR,
        relief=tk.FLAT,
        bd=0,
        highlightthickness=1,
        highlightbackground=CARD_BORDER,
        highlightcolor=PRIMARY_COLOR,
        font=("Segoe UI", 11),
    )


class AnimatedHero(tk.Canvas):
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent,
            width=176,
            height=176,
            bg=CARD_BG,
            bd=0,
            highlightthickness=0,
            **kwargs,
        )
        self.phase = 0
        self.after(0, self.animate)

    def animate(self):
        if not self.winfo_exists():
            return
        self.phase = (self.phase + 1) % 60
        self.draw()
        self.after(40, self.animate)

    def draw(self):
        self.delete("all")
        wave = abs(30 - self.phase) / 30.0
        pulse = 1.0 + (0.04 * (1.0 - wave))

        self.create_oval(8, 8, 168, 168, outline=GLOW_RING_ONE, width=2)
        self.create_oval(24, 24, 152, 152, outline=GLOW_RING_TWO, width=2)
        self.create_oval(40, 40, 136, 136, outline=GLOW_RING_THREE, width=2)

        size = 72 * pulse
        left = 88 - size / 2
        top = 88 - size / 2
        right = 88 + size / 2
        bottom = 88 + size / 2
        self.create_oval(left, top, right, bottom, fill=CARD_ALT_BG, outline="#2456a7", width=1)
        self.create_text(
            88,
            88,
            text="✋",
            fill="#67c7ff",
            font=("Segoe UI Emoji", 38),
        )
        self.create_line(122, 58, 136, 52, fill="#67c7ff", width=3, capstyle=tk.ROUND)
        self.create_line(126, 77, 142, 77, fill="#67c7ff", width=3, capstyle=tk.ROUND)
        self.create_line(118, 97, 132, 104, fill="#67c7ff", width=3, capstyle=tk.ROUND)


def create_pill(parent, label, value):
    pill = tk.Frame(
        parent,
        bg=PILL_BG,
        highlightthickness=1,
        highlightbackground=CARD_BORDER,
        highlightcolor=CARD_BORDER,
        bd=0,
        padx=12,
        pady=8,
    )
    tk.Label(
        pill,
        text=label,
        bg=PILL_BG,
        fg=MUTED_TEXT,
        font=("Segoe UI", 9),
    ).pack()
    value_label = tk.Label(
        pill,
        text=value,
        bg=PILL_BG,
        fg=TEXT_COLOR,
        font=("Segoe UI", 11, "bold"),
    )
    value_label.pack(pady=(2, 0))
    return pill, value_label


def truncate_middle(text, limit=68):
    if len(text) <= limit:
        return text
    part = max(10, (limit - 3) // 2)
    return f"{text[:part]}...{text[-part:]}"


def normalize_app_path(path):
    return os.path.normpath(path.strip().strip('"'))


def get_app_title(path):
    filename = os.path.basename(path)
    if not filename:
        return path
    name, _extension = os.path.splitext(filename)
    return name or filename


def get_app_badge(path):
    extension = os.path.splitext(path)[1].replace(".", "").upper()
    return (extension or "APP")[:3]


def configure_ui():
    config = load_config()
    result = {"action": None}
    apps = list(config["apps"])
    selection = {"index": 0 if apps else None}

    root = tk.Tk()
    root.title("Clap Trigger")
    root.configure(bg=WINDOW_BG)
    root.minsize(580, 840)
    center_window(root, 580, 840)
    apply_fade_in(root)

    shell = tk.Frame(root, bg=WINDOW_BG, padx=24, pady=22)
    shell.pack(fill="both", expand=True)

    hero_card = create_card(shell, padx=20, pady=18)
    hero_card.pack(fill="x", pady=(0, 14))

    hero_top = tk.Frame(hero_card, bg=CARD_BG)
    hero_top.pack(fill="x")

    release_badge = tk.Label(
        hero_top,
        text="Desktop Release",
        bg=PILL_BG,
        fg=PRIMARY_HOVER,
        font=("Segoe UI", 9, "bold"),
        padx=12,
        pady=6,
    )
    release_badge.pack(side="left")

    platform_badge = tk.Label(
        hero_top,
        text="Windows EXE",
        bg=CARD_BG,
        fg=MUTED_TEXT,
        font=("Segoe UI", 10),
    )
    platform_badge.pack(side="right")

    AnimatedHero(hero_card).pack(pady=(10, 8))

    title_row = tk.Frame(hero_card, bg=CARD_BG)
    title_row.pack()
    tk.Label(
        title_row,
        text="Clap",
        bg=CARD_BG,
        fg=TEXT_COLOR,
        font=("Segoe UI", 29, "bold"),
    ).pack(side="left")
    tk.Label(
        title_row,
        text=" Trigger",
        bg=CARD_BG,
        fg=PRIMARY_HOVER,
        font=("Segoe UI", 29, "bold"),
    ).pack(side="left")

    tk.Label(
        hero_card,
        text="Doble palmada para abrir apps",
        bg=CARD_BG,
        fg=MUTED_TEXT,
        font=("Segoe UI", 12),
    ).pack(pady=(4, 14))

    pills_row = tk.Frame(hero_card, bg=CARD_BG)
    pills_row.pack()
    apps_pill, apps_pill_value = create_pill(pills_row, "Apps", str(len(apps)))
    apps_pill.pack(side="left", padx=(0, 8))
    threshold_pill, threshold_pill_value = create_pill(
        pills_row,
        "Umbral",
        f"{clamp_threshold(config['threshold']):.1f} dB",
    )
    threshold_pill.pack(side="left", padx=8)
    mode_pill, _mode_pill_value = create_pill(
        pills_row,
        "Modo",
        "Auto-start" if startup_installed() else "Manual",
    )
    mode_pill.pack(side="left", padx=(8, 0))

    threshold_value = tk.DoubleVar(value=clamp_threshold(config["threshold"]))
    threshold_text = tk.StringVar(value=f"{threshold_value.get():.1f}")
    path_text = tk.StringVar()
    level_text = tk.StringVar(value=f"Nivel actual: 0.0 / umbral: {threshold_value.get():.1f}")
    apps_count_text = tk.StringVar(value=f"{len(apps)} configuradas")
    status_text = tk.StringVar(
        value="Inicio automatico activo." if startup_installed() else "Se activara en segundo plano al guardar."
    )
    status_color = {"value": MUTED_TEXT}

    def set_status(message, color=MUTED_TEXT):
        status_text.set(message)
        status_color["value"] = color
        status_label.configure(fg=color)
        status_dot.itemconfigure(status_dot_circle, fill=color, outline=color)

    threshold_card = create_card(shell)
    threshold_card.pack(fill="x", pady=(0, 14))

    tk.Label(
        threshold_card,
        text="Umbral de audio (0-90)",
        bg=CARD_BG,
        fg=TEXT_COLOR,
        font=("Segoe UI", 14, "bold"),
    ).pack(anchor="w")

    tk.Label(
        threshold_card,
        text="Sube o baja la sensibilidad para ajustar la deteccion de palmadas.",
        bg=CARD_BG,
        fg=MUTED_TEXT,
        font=("Segoe UI", 10),
    ).pack(anchor="w", pady=(4, 0))

    slider_row = tk.Frame(threshold_card, bg=CARD_BG)
    slider_row.pack(fill="x", pady=(14, 8))

    threshold_scale = tk.Scale(
        slider_row,
        from_=0,
        to=90,
        resolution=0.1,
        orient="horizontal",
        showvalue=False,
        variable=threshold_value,
        bg=CARD_BG,
        fg=MUTED_TEXT,
        activebackground=PRIMARY_HOVER,
        troughcolor=ENTRY_BG,
        highlightthickness=0,
        bd=0,
        relief=tk.FLAT,
        sliderlength=22,
        length=330,
    )
    threshold_scale.pack(side="left", fill="x", expand=True)

    threshold_entry = tk.Entry(
        slider_row,
        textvariable=threshold_text,
        width=7,
        justify="center",
    )
    style_entry(threshold_entry)
    threshold_entry.pack(side="left", padx=(14, 0), ipady=8)

    meter_row = tk.Frame(threshold_card, bg=CARD_BG)
    meter_row.pack(fill="x", pady=(8, 0))

    tk.Label(
        meter_row,
        textvariable=level_text,
        bg=CARD_BG,
        fg=MUTED_TEXT,
        font=("Segoe UI", 11),
    ).pack(side="left")

    tk.Label(
        meter_row,
        text="Escucha en segundo plano",
        bg=CARD_BG,
        fg=PRIMARY_HOVER,
        font=("Segoe UI", 10, "bold"),
    ).pack(side="right")

    def sync_threshold_from_slider():
        value = clamp_threshold(threshold_value.get())
        threshold_value.set(value)
        threshold_text.set(f"{value:.1f}")
        level_text.set(f"Nivel actual: 0.0 / umbral: {value:.1f}")
        threshold_pill_value.configure(text=f"{value:.1f} dB")

    def sync_threshold_from_entry(_event=None):
        try:
            value = clamp_threshold(float(threshold_text.get()))
        except ValueError:
            threshold_text.set(f"{threshold_value.get():.1f}")
            set_status("El umbral debe ser un numero valido.", ERROR_TEXT)
            return
        threshold_value.set(value)
        threshold_text.set(f"{value:.1f}")
        level_text.set(f"Nivel actual: 0.0 / umbral: {value:.1f}")
        threshold_pill_value.configure(text=f"{value:.1f} dB")

    threshold_scale.configure(command=lambda _value: sync_threshold_from_slider())
    threshold_entry.bind("<Return>", sync_threshold_from_entry)
    threshold_entry.bind("<FocusOut>", sync_threshold_from_entry)

    controls_card = create_card(shell, padx=14, pady=14)
    controls_card.pack(fill="x", pady=(0, 12))

    tk.Label(
        controls_card,
        text="Ruta de la app o acceso directo",
        bg=CARD_BG,
        fg=MUTED_TEXT,
        font=("Segoe UI", 10),
    ).pack(anchor="w")

    input_row = tk.Frame(controls_card, bg=CARD_BG)
    input_row.pack(fill="x", pady=(8, 10))

    path_entry = tk.Entry(input_row, textvariable=path_text)
    style_entry(path_entry)
    path_entry.pack(side="left", fill="x", expand=True, ipady=8)

    def choose_app():
        file_path = filedialog.askopenfilename(
            title="Seleccionar aplicacion",
            filetypes=[
                ("Aplicaciones y accesos", "*.exe *.lnk *.bat *.cmd"),
                ("Todos los archivos", "*.*"),
            ],
        )
        if file_path:
            path_text.set(file_path)

    browse_button = create_button(input_row, "Buscar", choose_app, primary=False)
    browse_button.pack(side="left", padx=(10, 0))

    row_actions = tk.Frame(controls_card, bg=CARD_BG)
    row_actions.pack(fill="x", pady=(0, 10))

    def add_app_from_input():
        raw_path = normalize_app_path(path_text.get())
        if not raw_path:
            set_status("Escribe o selecciona una aplicacion.", ERROR_TEXT)
            return
        if not os.path.exists(raw_path):
            set_status("La ruta indicada no existe.", ERROR_TEXT)
            return
        if raw_path in apps:
            set_status("Esa aplicacion ya esta en la lista.", ERROR_TEXT)
            return

        apps.append(raw_path)
        selection["index"] = len(apps) - 1
        path_text.set("")
        render_apps()
        set_status("Aplicacion agregada.", SUCCESS_TEXT)

    def remove_selected_app():
        if selection["index"] is None or not apps:
            set_status("No hay ninguna app seleccionada.", ERROR_TEXT)
            return

        del apps[selection["index"]]
        if not apps:
            selection["index"] = None
        else:
            selection["index"] = min(selection["index"], len(apps) - 1)
        render_apps()
        set_status("Aplicacion eliminada.", MUTED_TEXT)

    add_button = create_button(row_actions, "Agregar a la lista", add_app_from_input, primary=False)
    add_button.pack(side="left", fill="x", expand=True)

    remove_button = create_button(row_actions, "Eliminar seleccionada", remove_selected_app, primary=False)
    remove_button.pack(side="left", fill="x", expand=True, padx=(10, 0))

    tip_card = tk.Frame(
        shell,
        bg=TIP_BG,
        highlightthickness=1,
        highlightbackground=CARD_BORDER,
        highlightcolor=CARD_BORDER,
        bd=0,
        padx=14,
        pady=12,
    )
    tip_card.pack(fill="x", pady=(0, 12))

    tip_icon = tk.Frame(tip_card, bg=PRIMARY_COLOR, width=34, height=34)
    tip_icon.pack(side="left")
    tip_icon.pack_propagate(False)
    tk.Label(
        tip_icon,
        text="i",
        bg=PRIMARY_COLOR,
        fg=TEXT_COLOR,
        font=("Segoe UI", 12, "bold"),
    ).pack(expand=True)

    tip_text = tk.Frame(tip_card, bg=TIP_BG)
    tip_text.pack(side="left", fill="x", expand=True, padx=(12, 0))
    tk.Label(
        tip_text,
        text="Consejo",
        bg=TIP_BG,
        fg=PRIMARY_HOVER,
        font=("Segoe UI", 10, "bold"),
    ).pack(anchor="w")
    tk.Label(
        tip_text,
        text="Ajusta el umbral de audio para mejorar la deteccion y usa accesos directos si no quieres rutas largas.",
        bg=TIP_BG,
        fg=MUTED_TEXT,
        font=("Segoe UI", 10),
        wraplength=410,
        justify="left",
    ).pack(anchor="w", pady=(4, 0))

    row_save = tk.Frame(controls_card, bg=CARD_BG)
    row_save.pack(fill="x")

    def save_config_ui(start_after_save=False):
        sync_threshold_from_entry()
        threshold = threshold_value.get()

        if start_after_save and not apps:
            set_status("Anade al menos una app antes de activar.", ERROR_TEXT)
            return

        new_config = {"threshold": threshold, "apps": apps}
        if not save_config(new_config):
            set_status("No se pudo guardar la configuracion.", ERROR_TEXT)
            return

        set_status("Configuracion guardada.", SUCCESS_TEXT)
        result["action"] = "start" if start_after_save else "saved"
        if start_after_save:
            root.after(120, root.destroy)

    save_button = create_button(row_save, "Guardar", lambda: save_config_ui(False), primary=True)
    save_button.pack(side="left", fill="x", expand=True)

    start_button = create_button(row_save, "Guardar y activar", lambda: save_config_ui(True), primary=True)
    start_button.pack(side="left", fill="x", expand=True, padx=(10, 0))

    apps_title = tk.Frame(shell, bg=WINDOW_BG)
    apps_title.pack(fill="x", pady=(0, 8))
    tk.Label(
        apps_title,
        text="Apps seleccionadas:",
        bg=WINDOW_BG,
        fg=TEXT_COLOR,
        font=("Segoe UI", 14, "bold"),
    ).pack(side="left")

    tk.Label(
        apps_title,
        textvariable=apps_count_text,
        bg=WINDOW_BG,
        fg=MUTED_TEXT,
        font=("Segoe UI", 10),
    ).pack(side="right")

    apps_card = create_card(shell, padx=12, pady=12)
    apps_card.pack(fill="both", expand=True, pady=(0, 14))

    apps_canvas = tk.Canvas(
        apps_card,
        bg=CARD_BG,
        highlightthickness=0,
        bd=0,
    )
    apps_scrollbar = tk.Scrollbar(
        apps_card,
        orient="vertical",
        command=apps_canvas.yview,
        bg=CARD_ALT_BG,
        troughcolor=CARD_BG,
        activebackground=PRIMARY_COLOR,
        relief=tk.FLAT,
        bd=0,
        highlightthickness=0,
        width=12,
    )
    apps_inner = tk.Frame(apps_canvas, bg=CARD_BG)
    apps_window = apps_canvas.create_window((0, 0), window=apps_inner, anchor="nw")
    apps_canvas.configure(yscrollcommand=apps_scrollbar.set)
    apps_canvas.pack(side="left", fill="both", expand=True)
    apps_scrollbar.pack(side="right", fill="y")

    def on_apps_configure(_event=None):
        apps_canvas.configure(scrollregion=apps_canvas.bbox("all"))

    def on_apps_canvas_resize(event):
        apps_canvas.itemconfigure(apps_window, width=event.width)

    apps_inner.bind("<Configure>", on_apps_configure)
    apps_canvas.bind("<Configure>", on_apps_canvas_resize)

    def select_app(index):
        selection["index"] = index
        render_apps()

    def bind_click(widget, index):
        widget.bind("<Button-1>", lambda _event, idx=index: select_app(idx))

    def render_apps():
        for child in apps_inner.winfo_children():
            child.destroy()

        apps_count_text.set(f"{len(apps)} configuradas")
        apps_pill_value.configure(text=str(len(apps)))

        if not apps:
            empty_box = tk.Frame(apps_inner, bg=CARD_BG, pady=22)
            empty_box.pack(fill="x")
            tk.Label(
                empty_box,
                text="No hay apps agregadas todavia",
                bg=CARD_BG,
                fg=TEXT_COLOR,
                font=("Segoe UI", 12, "bold"),
            ).pack()
            tk.Label(
                empty_box,
                text="Agrega archivos .exe, accesos directos o scripts desde el panel superior.",
                bg=CARD_BG,
                fg=MUTED_TEXT,
                font=("Segoe UI", 10),
                wraplength=420,
                justify="center",
            ).pack(pady=(6, 0))
            return

        for index, path in enumerate(apps):
            selected = index == selection["index"]
            row_bg = ROW_SELECTED if selected else CARD_ALT_BG
            border = PRIMARY_COLOR if selected else CARD_BORDER

            row = tk.Frame(
                apps_inner,
                bg=row_bg,
                highlightthickness=1,
                highlightbackground=border,
                highlightcolor=border,
                bd=0,
                padx=0,
                pady=10,
            )
            row.pack(fill="x", pady=(0, 8))

            accent_strip = tk.Frame(row, bg=PRIMARY_HOVER if selected else row_bg, width=4)
            accent_strip.pack(side="left", fill="y")

            content_row = tk.Frame(row, bg=row_bg, padx=12)
            content_row.pack(side="left", fill="both", expand=True)

            icon_box = tk.Frame(content_row, bg=ICON_BG, width=42, height=42)
            icon_box.pack(side="left")
            icon_box.pack_propagate(False)
            icon_label = tk.Label(
                icon_box,
                text=get_app_badge(path),
                bg=ICON_BG,
                fg=TEXT_COLOR,
                font=("Segoe UI", 9, "bold"),
            )
            icon_label.pack(expand=True)

            text_box = tk.Frame(content_row, bg=row_bg)
            text_box.pack(side="left", fill="both", expand=True, padx=12)

            title_label = tk.Label(
                text_box,
                text=get_app_title(path),
                bg=row_bg,
                fg=TEXT_COLOR,
                anchor="w",
                justify="left",
                font=("Segoe UI", 12, "bold"),
            )
            title_label.pack(fill="x")

            subtitle_label = tk.Label(
                text_box,
                text=truncate_middle(path),
                bg=row_bg,
                fg=MUTED_TEXT,
                anchor="w",
                justify="left",
                wraplength=350,
                font=("Segoe UI", 9),
            )
            subtitle_label.pack(fill="x", pady=(2, 0))

            chevron_label = tk.Label(
                content_row,
                text="✓" if selected else ">",
                bg=row_bg,
                fg=PRIMARY_HOVER if selected else MUTED_TEXT,
                font=("Segoe UI", 16, "bold"),
                width=2,
            )
            chevron_label.pack(side="right")

            for widget in (
                row,
                accent_strip,
                content_row,
                icon_box,
                icon_label,
                text_box,
                title_label,
                subtitle_label,
                chevron_label,
            ):
                bind_click(widget, index)

    status_row = tk.Frame(shell, bg=WINDOW_BG)
    status_row.pack(fill="x")
    status_dot = tk.Canvas(
        status_row,
        width=14,
        height=14,
        bg=WINDOW_BG,
        bd=0,
        highlightthickness=0,
    )
    status_dot_circle = status_dot.create_oval(2, 2, 12, 12, fill=status_color["value"], outline=status_color["value"])
    status_dot.pack(side="left", pady=10)

    status_label = tk.Label(
        status_row,
        textvariable=status_text,
        bg=WINDOW_BG,
        fg=status_color["value"],
        font=("Segoe UI", 11),
        padx=8,
        pady=8,
    )
    status_label.pack(side="left")

    root.bind("<Escape>", lambda _event: root.destroy())
    path_entry.bind("<Return>", lambda _event: add_app_from_input())
    path_entry.focus_set()

    render_apps()
    root.mainloop()
    return result["action"]


def configure():
    if not startup_installed():
        installed = install_startup()
        if installed:
            print("Arranque automatico configurado en segundo plano.")
        else:
            print("No se pudo configurar el arranque automatico.")

    return configure_ui()


def main(args):
    if not startup_installed():
        installed = install_startup()
        if installed:
            print("Arranque automatico configurado en segundo plano.")
        else:
            print("No se pudo configurar el arranque automatico.")

    config = load_config()
    threshold = args.threshold if args.threshold is not None else config["threshold"]
    apps = config["apps"]
    listen_forever(threshold, apps)


if __name__ == "__main__":
    args = parse_args()

    if args.uninstall:
        if uninstall_startup():
            print("Arranque automatico eliminado.")
        else:
            print("No se encontro el archivo de inicio automatico.")
    elif args.configure:
        action = configure()
        if action == "start":
            background_args = argparse.Namespace(
                threshold=args.threshold,
                configure=False,
                uninstall=False,
                background=True,
            )
            main(background_args)
    elif is_frozen_app() and not args.background:
        action = configure()
        if action == "start":
            background_args = argparse.Namespace(
                threshold=args.threshold,
                configure=False,
                uninstall=False,
                background=True,
            )
            main(background_args)
        else:
            sys.exit(0)
    else:
        current_config = load_config()
        if is_frozen_app() and not current_config.get("apps"):
            sys.exit(0)
        main(args)
