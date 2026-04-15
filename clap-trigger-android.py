import json
import os
import time
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.listview import ListView
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from kivy.clock import Clock
import numpy as np
import audiostream  # Necesitas instalar audiostream para Android

# --- CONFIGURACIÓN por defecto ---
DEFAULT_THRESHOLD = 30.0
MIN_INTERVAL = 0.1
MAX_INTERVAL = 1.0
DEFAULT_APPS = []
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clap-config.json")

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
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False


class ClapTriggerApp(App):
    def build(self):
        self.config = load_config()
        self.threshold = self.config["threshold"]
        self.apps = self.config["apps"]
        self.listening = False
        self.last_clap_time = 0

        layout = BoxLayout(orientation='vertical')

        # Umbral
        layout.add_widget(Label(text="Umbral (dB):"))
        self.threshold_input = TextInput(text=str(self.threshold), multiline=False)
        layout.add_widget(self.threshold_input)

        # Lista de apps
        layout.add_widget(Label(text="Aplicaciones:"))
        self.apps_list = ListView()
        self.update_apps_list()
        layout.add_widget(self.apps_list)

        # Botones
        button_layout = BoxLayout(size_hint_y=None, height=50)
        button_layout.add_widget(Button(text="Agregar App", on_press=self.add_app))
        button_layout.add_widget(Button(text="Eliminar App", on_press=self.remove_app))
        button_layout.add_widget(Button(text="Guardar", on_press=self.save_config))
        layout.add_widget(button_layout)

        # Botón de escuchar
        self.listen_button = Button(text="Iniciar Clap Trigger", on_press=self.toggle_listen)
        layout.add_widget(self.listen_button)

        return layout

    def update_apps_list(self):
        self.apps_list.adapter.data = self.apps
        self.apps_list.adapter.notifyDataSetChanged()

    def add_app(self, instance):
        # En Android, usar filechooser o algo, pero para simplicidad, popup con input
        popup = Popup(title="Agregar Aplicación", size_hint=(0.8, 0.8))
        content = BoxLayout(orientation='vertical')
        file_input = TextInput(hint_text="Ruta de la app")
        content.add_widget(file_input)
        btn_layout = BoxLayout(size_hint_y=None, height=50)
        btn_layout.add_widget(Button(text="Cancelar", on_press=popup.dismiss))
        btn_layout.add_widget(Button(text="Agregar", on_press=lambda x: self.do_add_app(file_input.text, popup)))
        content.add_widget(btn_layout)
        popup.content = content
        popup.open()

    def do_add_app(self, path, popup):
        if path:
            self.apps.append(path)
            self.update_apps_list()
        popup.dismiss()

    def remove_app(self, instance):
        if self.apps:
            selected = self.apps_list.adapter.selection
            if selected:
                self.apps.remove(selected[0].text)
                self.update_apps_list()

    def save_config(self, instance):
        try:
            self.threshold = float(self.threshold_input.text)
            self.config = {"threshold": self.threshold, "apps": self.apps}
            if save_config(self.config):
                popup = Popup(title="Éxito", content=Label(text="Configuración guardada."), size_hint=(0.5, 0.5))
                popup.open()
            else:
                popup = Popup(title="Error", content=Label(text="No se pudo guardar."), size_hint=(0.5, 0.5))
                popup.open()
        except ValueError:
            popup = Popup(title="Error", content=Label(text="Umbral inválido."), size_hint=(0.5, 0.5))
            popup.open()

    def toggle_listen(self, instance):
        if self.listening:
            self.stop_listening()
        else:
            self.start_listening()

    def start_listening(self):
        self.listening = True
        self.listen_button.text = "Detener Clap Trigger"
        # Iniciar audio stream
        self.stream = audiostream.start(self.on_audio_data, rate=44100, channels=1)
        print(f"Escuchando... (Umbral: {self.threshold} dB)")

    def stop_listening(self):
        self.listening = False
        self.listen_button.text = "Iniciar Clap Trigger"
        if hasattr(self, 'stream'):
            audiostream.stop(self.stream)
        print("Detenido.")

    def on_audio_data(self, data):
        # Procesar audio para detectar claps
        volume = np.linalg.norm(np.frombuffer(data, dtype=np.int16)) / len(data)
        db = 20 * np.log10(volume) if volume > 0 else 0

        if db > self.threshold:
            now = time.time()
            if MIN_INTERVAL < (now - self.last_clap_time) < MAX_INTERVAL:
                self.launch_apps()
                self.last_clap_time = 0
            else:
                self.last_clap_time = now
                print(f"[*] Palmada 1 detectada ({db:.1f} dB)")

    def launch_apps(self):
        print("¡DOBLE PALMADA detectada! Abriendo aplicaciones...")
        for app in self.apps:
            # En Android, usar intent o algo para abrir apps
            # Para simplicidad, asumir que son paquetes
            try:
                import android
                android.startActivity(app)  # Asumiendo que app es package name
            except ImportError:
                print(f"Abriendo: {app}")


if __name__ == "__main__":
    ClapTriggerApp().run()