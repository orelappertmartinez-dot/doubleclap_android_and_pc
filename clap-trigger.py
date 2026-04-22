import argparse
import json
import os
import sys
import threading
import time

import numpy as np
import sounddevice as sd
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

# --- CONFIGURACIÓN por defecto ---
DEFAULT_THRESHOLD = 30.0
MIN_INTERVAL = 0.1
MAX_INTERVAL = 1.0
DEFAULT_APPS = []
APP_DIR_NAME = "ClapTrigger"
STARTUP_NAME = "clap-trigger-startup.vbs"


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
    parser.add_argument("-t", "--threshold", type=float,
                        help="Umbral en dB. Valores más bajos hacen la detección más sensible.")
    parser.add_argument("--configure", action="store_true",
                        help="Abrir el configurador con interfaz gráfica.")
    parser.add_argument("--uninstall", action="store_true",
                        help="Eliminar el arranque automático de Windows.")
    return parser.parse_args()


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"threshold": DEFAULT_THRESHOLD, "apps": DEFAULT_APPS.copy()}

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        threshold = float(data.get("threshold", DEFAULT_THRESHOLD))
        apps = data.get("apps", DEFAULT_APPS.copy())
        if not isinstance(apps, list):
            apps = DEFAULT_APPS.copy()
        return {"threshold": threshold, "apps": apps}
    except (ValueError, OSError, json.JSONDecodeError):
        return {"threshold": DEFAULT_THRESHOLD, "apps": DEFAULT_APPS.copy()}


def save_config(config):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False


def get_startup_folder():
    return os.path.join(os.environ.get("APPDATA", ""),
                        "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def get_pythonw_executable():
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        candidate = exe[:-4] + "w.exe"
        if os.path.exists(candidate):
            return candidate
    return exe


def get_launch_command():
    if is_frozen_app():
        return [os.path.abspath(sys.executable)]
    return [get_pythonw_executable(), os.path.abspath(__file__)]


def get_startup_script_path():
    return os.path.join(get_startup_folder(), STARTUP_NAME)


def install_startup():
    startup_folder = get_startup_folder()
    if not startup_folder or not os.path.isdir(startup_folder):
        return False

    vbs_path = get_startup_script_path()
    command_parts = get_launch_command()
    quoted_parts = [f'"""" & "{part}" & """"' for part in command_parts]
    command_expr = ' & " " & '.join(quoted_parts)

    content = 'Set WshShell = CreateObject("WScript.Shell")\n'
    content += f'cmd = {command_expr}\n'
    content += 'WshShell.Run cmd, 0, false\n'

    if os.path.exists(vbs_path):
        return True

    try:
        with open(vbs_path, "w", encoding="utf-8") as f:
            f.write(content)
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
    print("  ¡DOBLE PALMADA detectada! Abriendo aplicaciones...")
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
        print("No hay aplicaciones configuradas. Abre el configurador para añadirlas.")
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


def configure_ui():
    config = load_config()
    result = {"action": None}

    root = tk.Tk()
    root.title("Clap Trigger")
    root.geometry("640x540")
    root.minsize(640, 540)

    tk.Label(root, text="Umbral (dB):").pack(pady=5)
    threshold_entry = tk.Entry(root)
    threshold_entry.insert(0, str(config["threshold"]))
    threshold_entry.pack(pady=5)

    tk.Label(root, text="Aplicaciones a abrir:").pack(pady=5)

    frame = tk.Frame(root)
    frame.pack(pady=5)

    apps_listbox = tk.Listbox(frame, height=10, width=70)
    for app in config["apps"]:
        apps_listbox.insert(tk.END, app)
    apps_listbox.pack(side=tk.LEFT)

    scrollbar = tk.Scrollbar(frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    apps_listbox.config(yscrollcommand=scrollbar.set)
    scrollbar.config(command=apps_listbox.yview)

    def add_app():
        file_path = filedialog.askopenfilename(
            title="Seleccionar aplicación",
            filetypes=[("Archivos ejecutables", "*.exe"), ("Enlaces", "*.lnk"), ("Todos los archivos", "*.*")]
        )
        if file_path:
            apps_listbox.insert(tk.END, file_path)

    def remove_app():
        selected = apps_listbox.curselection()
        if selected:
            apps_listbox.delete(selected[0])

    button_frame = tk.Frame(root)
    button_frame.pack(pady=5)

    tk.Button(button_frame, text="Agregar aplicación", command=add_app).pack(side=tk.LEFT, padx=5)
    tk.Button(button_frame, text="Eliminar seleccionada", command=remove_app).pack(side=tk.LEFT, padx=5)

    def save_config_ui(start_after_save=False):
        try:
            threshold = float(threshold_entry.get())
            apps = list(apps_listbox.get(0, tk.END))
            new_config = {"threshold": threshold, "apps": apps}
            if save_config(new_config):
                result["action"] = "start" if start_after_save else "saved"
                messagebox.showinfo("Éxito", "Configuración guardada.")
                if start_after_save:
                    root.destroy()
            else:
                messagebox.showerror("Error", "No se pudo guardar la configuración.")
        except ValueError:
            messagebox.showerror("Error", "Umbral debe ser un número válido.")

    action_frame = tk.Frame(root)
    action_frame.pack(pady=10)

    tk.Button(
        action_frame,
        text="Guardar configuración",
        command=lambda: save_config_ui(False)
    ).pack(side=tk.LEFT, padx=5)

    tk.Button(
        action_frame,
        text="Guardar y activar",
        command=lambda: save_config_ui(True)
    ).pack(side=tk.LEFT, padx=5)

    root.mainloop()
    return result["action"]


def configure():
    if not startup_installed():
        installed = install_startup()
        if installed:
            print("Arranque automático configurado en segundo plano.")
        else:
            print("No se pudo configurar el arranque automático.")

    return configure_ui()


def main(args):
    if not startup_installed():
        installed = install_startup()
        if installed:
            print("Arranque automático configurado en segundo plano.")
        else:
            print("No se pudo configurar el arranque automático.")

    config = load_config()
    threshold = args.threshold if args.threshold is not None else config["threshold"]
    apps = config["apps"]
    listen_forever(threshold, apps)


if __name__ == "__main__":
    args = parse_args()
    if args.uninstall:
        if uninstall_startup():
            print("Arranque automático eliminado.")
        else:
            print("No se encontró el archivo de inicio automático.")
    elif args.configure:
        action = configure()
        if action == "start":
            main(parse_args())
    else:
        current_config = load_config()
        if is_frozen_app() and not current_config.get("apps"):
            action = configure()
            if action != "start":
                sys.exit(0)
        main(args)
