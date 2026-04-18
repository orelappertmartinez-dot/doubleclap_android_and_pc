import json
import os
import time

from kivy.app import App
from kivy.clock import mainthread
from kivy.metrics import dp
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

try:
    from android.permissions import Permission, check_permission, request_permissions
except ImportError:
    Permission = None
    check_permission = None
    request_permissions = None


DEFAULT_THRESHOLD = 30.0
MIN_INTERVAL = 0.1
MAX_INTERVAL = 1.0
DEFAULT_APPS = []
PACKAGED_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clap-config.json")


def default_config():
    return {"threshold": DEFAULT_THRESHOLD, "apps": DEFAULT_APPS.copy()}


def get_numpy_module():
    import numpy

    return numpy


def get_audiostream_module():
    import audiostream

    return audiostream


def get_config_path():
    app = App.get_running_app()
    if app is not None and getattr(app, "user_data_dir", None):
        return os.path.join(app.user_data_dir, "clap-config.json")
    return PACKAGED_CONFIG_FILE


def load_config():
    config_path = get_config_path()
    source_path = config_path if os.path.exists(config_path) else PACKAGED_CONFIG_FILE
    if not os.path.exists(source_path):
        return default_config()

    try:
        with open(source_path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError, json.JSONDecodeError):
        return default_config()

    threshold = float(data.get("threshold", DEFAULT_THRESHOLD))
    apps = data.get("apps", DEFAULT_APPS.copy())
    if not isinstance(apps, list):
        apps = DEFAULT_APPS.copy()
    return {"threshold": threshold, "apps": apps}


def save_config(config):
    try:
        config_path = get_config_path()
        config_dir = os.path.dirname(config_path)
        if config_dir:
            os.makedirs(config_dir, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as file:
            json.dump(config, file, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False


class ClapTriggerApp(App):
    def build(self):
        self.title = "Clap Trigger"
        self.config_data = load_config()
        self.threshold = self.config_data["threshold"]
        self.apps = list(self.config_data["apps"])
        self.last_clap_time = 0.0
        self.listening = False
        self.stream = None
        self.audio_backend = None
        self.audio_permission_granted = platform != "android"

        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))

        root.add_widget(Label(text="Umbral (dB):", size_hint_y=None, height=dp(30)))
        self.threshold_input = TextInput(
            text=str(self.threshold),
            multiline=False,
            size_hint_y=None,
            height=dp(44),
        )
        root.add_widget(self.threshold_input)

        root.add_widget(Label(text="Paquetes Android:", size_hint_y=None, height=dp(30)))
        scroll = ScrollView(size_hint=(1, 1))
        self.apps_label = Label(
            text="",
            markup=False,
            halign="left",
            valign="top",
            size_hint_y=None,
            text_size=(0, None),
        )
        self.apps_label.bind(width=self._update_label_wrap)
        scroll.add_widget(self.apps_label)
        root.add_widget(scroll)

        self.app_input = TextInput(
            hint_text="com.spotify.music",
            multiline=False,
            size_hint_y=None,
            height=dp(44),
        )
        root.add_widget(self.app_input)

        button_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        button_row.add_widget(Button(text="Agregar", on_press=self.add_app))
        button_row.add_widget(Button(text="Eliminar ultima", on_press=self.remove_last_app))
        root.add_widget(button_row)

        action_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        action_row.add_widget(Button(text="Guardar", on_press=self.persist_config))
        self.listen_button = Button(text="Iniciar", on_press=self.toggle_listen)
        action_row.add_widget(self.listen_button)
        root.add_widget(action_row)

        self.status_label = Label(
            text="Configura los paquetes y pulsa Iniciar.",
            size_hint_y=None,
            height=dp(50),
        )
        root.add_widget(self.status_label)

        self.refresh_apps_label()
        return root

    def on_start(self):
        self.request_android_permissions()

    def _update_label_wrap(self, instance, width):
        instance.text_size = (max(width - dp(16), 0), None)
        instance.texture_update()
        instance.height = max(instance.texture_size[1] + dp(12), dp(40))

    def refresh_apps_label(self):
        if self.apps:
            self.apps_label.text = "\n".join(f"- {app}" for app in self.apps)
        else:
            self.apps_label.text = "No hay paquetes configurados."
        self._update_label_wrap(self.apps_label, self.apps_label.width or dp(200))

    def show_popup(self, title, message):
        Popup(
            title=title,
            content=Label(text=message),
            size_hint=(0.8, 0.4),
        ).open()

    def request_android_permissions(self):
        if platform != "android" or Permission is None:
            return

        wanted_permissions = [Permission.RECORD_AUDIO]
        notification_permission = getattr(Permission, "POST_NOTIFICATIONS", None)
        if notification_permission:
            wanted_permissions.append(notification_permission)

        missing_permissions = [
            permission
            for permission in wanted_permissions
            if check_permission is not None and not check_permission(permission)
        ]

        if not missing_permissions:
            self.audio_permission_granted = True
            self.status_label.text = "Permisos Android concedidos. Puedes iniciar la escucha."
            return

        self.status_label.text = "Solicitando permisos Android..."
        request_permissions(missing_permissions, self.on_permissions_result)

    @mainthread
    def on_permissions_result(self, permissions, grants):
        results = dict(zip(permissions, grants))
        record_audio_permission = getattr(Permission, "RECORD_AUDIO", None)
        self.audio_permission_granted = bool(results.get(record_audio_permission, False))

        if self.audio_permission_granted:
            self.status_label.text = "Permiso de microfono concedido. Puedes iniciar la escucha."
        else:
            self.status_label.text = "Permiso de microfono denegado. La app no puede escuchar palmadas."
            self.show_popup(
                "Permiso requerido",
                "Debes conceder acceso al microfono para que Clap Trigger funcione.",
            )

    def add_app(self, _instance):
        package_name = self.app_input.text.strip()
        if not package_name:
            self.show_popup("Aviso", "Escribe un nombre de paquete Android.")
            return
        if package_name in self.apps:
            self.show_popup("Aviso", "Ese paquete ya esta en la lista.")
            return

        self.apps.append(package_name)
        self.app_input.text = ""
        self.refresh_apps_label()

    def remove_last_app(self, _instance):
        if self.apps:
            self.apps.pop()
            self.refresh_apps_label()

    def persist_config(self, _instance):
        try:
            self.threshold = float(self.threshold_input.text)
        except ValueError:
            self.show_popup("Error", "El umbral debe ser un numero valido.")
            return False

        self.config_data = {"threshold": self.threshold, "apps": self.apps}
        if save_config(self.config_data):
            self.status_label.text = "Configuracion guardada."
            return True

        self.show_popup("Error", "No se pudo guardar la configuracion.")
        return False

    def toggle_listen(self, _instance):
        if self.listening:
            self.stop_listening()
        else:
            self.start_listening()

    def start_listening(self):
        if not self.persist_config(None):
            return

        if platform == "android" and not self.audio_permission_granted:
            self.request_android_permissions()
            self.show_popup(
                "Permiso requerido",
                "Concede el permiso de microfono y vuelve a pulsar Iniciar.",
            )
            return

        try:
            self.audio_backend = get_audiostream_module()
            get_numpy_module()
        except Exception as exc:
            self.audio_backend = None
            self.show_popup("Error", f"No se pudieron cargar las librerias de audio:\n{exc}")
            return

        try:
            self.stream = self.audio_backend.start(self.on_audio_data, rate=44100, channels=1)
        except Exception as exc:
            self.stream = None
            self.show_popup("Error", f"No se pudo abrir el microfono:\n{exc}")
            return

        self.listening = True
        self.listen_button.text = "Detener"
        self.status_label.text = f"Escuchando... umbral {self.threshold:.1f} dB"

    def stop_listening(self):
        if self.stream is not None and self.audio_backend is not None:
            try:
                self.audio_backend.stop(self.stream)
            except Exception:
                pass
            self.stream = None

        self.listening = False
        self.listen_button.text = "Iniciar"
        self.status_label.text = "Detenido."

    def on_audio_data(self, data):
        try:
            numpy = get_numpy_module()
        except Exception as exc:
            self.update_status(f"Error cargando numpy: {exc}")
            self.stop_listening()
            return

        samples = numpy.frombuffer(data, dtype=numpy.int16)
        if samples.size == 0:
            return

        volume = numpy.linalg.norm(samples) / samples.size
        db = 20 * numpy.log10(volume) if volume > 0 else 0

        if db <= self.threshold:
            return

        now = time.time()
        if MIN_INTERVAL < (now - self.last_clap_time) < MAX_INTERVAL:
            self.last_clap_time = 0
            self.launch_apps()
        else:
            self.last_clap_time = now
            self.update_status(f"Palmada detectada ({db:.1f} dB)")

    @mainthread
    def update_status(self, message):
        self.status_label.text = message

    @mainthread
    def launch_apps(self):
        if not self.apps:
            self.status_label.text = "No hay paquetes configurados para abrir."
            return

        try:
            from jnius import autoclass
        except ImportError:
            self.status_label.text = "pyjnius no esta disponible en esta compilacion."
            return

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        current_activity = PythonActivity.mActivity
        package_manager = current_activity.getPackageManager()

        opened = 0
        for package_name in self.apps:
            intent = package_manager.getLaunchIntentForPackage(package_name)
            if intent is None:
                continue
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            current_activity.startActivity(intent)
            opened += 1

        if opened:
            self.status_label.text = f"Doble palmada detectada. Apps abiertas: {opened}"
        else:
            self.status_label.text = "No se pudo abrir ninguna app. Revisa los paquetes."

    def on_stop(self):
        self.stop_listening()
