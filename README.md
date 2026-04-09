# Workspace Launcher

Automatic work environment launcher for Windows. Launches configured apps, browsers and terminals, placing them on selected monitors — all with a single gesture.

**Launch methods:**
- Double clap (sound detection with PANNs CNN14 neural network)
- Voice command (offline speech recognition via Vosk)
- Keyboard shortcut (e.g. `Win+Shift+W`)
- System tray icon

---

## Features

- **Profiles** — prepare different app sets (e.g. "Work", "Home", "Project X") and switch between them
- **Window positioning** — assign apps to specific monitors, screen halves (left/right) and layers (on top / behind)
- **Smart launching** — detects already running apps and just repositions them instead of launching again
- **Sound recognition** — PANNs CNN14 neural network classifies sounds (clapping, snapping, whistling, knocking and more)
- **Voice command** — offline, no data sent to the cloud (Vosk model)
- **UWP support** — automatically detects and launches Microsoft Store apps (Teams, Spotify etc.)
- **Configuration GUI** — graphical editor for profiles, apps and settings (customtkinter)
- **Autostart** — optional launch at Windows startup

---

## Requirements

- **Windows 10/11**
- **Python 3.10+** (to run from source)
- **Microphone** (for clap detection and voice commands)
- Optionally: **Git Bash**, **AutoHotkey v2**

---

## Installation

### Option A: From source (recommended for developers)

```bash
# Clone the repository
git clone https://github.com/YOUR-USER/workspace-launcher.git
cd workspace-launcher

# Install dependencies
pip install -r requirements.txt

# Run the configurator
python config_gui.py

# Run the launcher
python workspace.py
```

### Option B: Compiled .exe

```bash
# Build .exe files
build.bat

# Output in dist/ folder:
#   WorkspaceLauncher.exe  — main application
#   workspace-config.json  — configuration
```

Copy `dist/WorkspaceLauncher.exe` + `dist/workspace-config.json` to any computer — no Python required.

---

## Usage

### 1. Configuration (GUI)

Run the configurator:

```bash
python config_gui.py
# or
WorkspaceConfig.exe
```

In the configurator:
- **"Apps" tab** — add apps from the installed programs list or browse for .exe
- **"Terminals" tab** — add terminals (Git Bash, PowerShell, CMD, Windows Terminal) with startup commands
- **"Settings" tab** — set microphone sensitivity, keyboard shortcut, trigger sound, voice commands

For each app/terminal you can set:
| Option | Description |
|--------|-------------|
| Screen | Monitor number (1, 2, 3...) |
| Position | `full`, `left` half, `right` half |
| Layer | `Normal`, `On top`, `Behind` |
| Order | Launch priority (higher = earlier) |
| Minimize | Launch minimized |

### 2. Running the launcher

```bash
python workspace.py
# or
WorkspaceLauncher.exe
```

The application:
1. Starts in the system tray
2. Loads the sound recognition model (~80 MB, one-time)
3. Listens on the microphone — displays volume bar in the console
4. After detecting a double clap (or hotkey/voice command) launches the active profile

### 3. Triggering workspace

| Method | Default setting |
|--------|-----------------|
| Clap | 2x hand clap |
| Hotkey | `Win+Shift+W` |
| Voice command | Set in configuration (e.g. "launch") |
| Tray icon | Right-click > "Launch: [profile]" |

### 4. Tray menu

Right-click the tray icon:
- **Launch: [profile]** — launch selected profile
- **Close workspace** — close all launched processes
- **Configuration** — open configuration GUI
- **Quit** — close Workspace Launcher

---

## Configuration (JSON)

The `workspace-config.json` file is created automatically by the GUI. Example configuration:

```json
{
  "czulosc_klasniecia": 70,
  "hotkey": "Win+Shift+W",
  "zdarzenie_dzwiekowe": "Clapping",
  "liczba_zdarzen": 2,
  "cooldown": 3,
  "czulosc_nn": 0.12,
  "slowa_kluczowe": "launch",
  "jezyk_mowy": "en",
  "profil_aktywny": "Work",
  "profile": {
    "Work": {
      "aplikacje": [
        {
          "nazwa": "VS Code",
          "exe": "code",
          "argumenty": "C:\\Projects\\my-app",
          "ekran": 1,
          "polowa": "",
          "warstwa": "Normal",
          "kolejnosc": 0,
          "minimalizuj": false
        }
      ],
      "terminale": [
        {
          "nazwa": "Dev Server",
          "terminal_typ": "Git Bash",
          "folder": "C:\\Projects\\my-app",
          "komenda": "npm run dev",
          "ekran": 2,
          "polowa": "right",
          "warstwa": "On top"
        }
      ]
    }
  }
}
```

Full example in [`workspace-config.example.json`](workspace-config.example.json).

### Configuration options

| Key | Type | Description |
|-----|------|-------------|
| `czulosc_klasniecia` | int (40-95) | Microphone volume threshold in dB |
| `hotkey` | string | Keyboard shortcut, e.g. `Win+Shift+W`, `Ctrl+Alt+S` |
| `zdarzenie_dzwiekowe` | string | Sound type: `Clapping`, `Finger snapping`, `Whistling`, `Knock`, `Bell` etc. |
| `liczba_zdarzen` | int (1-3) | How many times to repeat the sound to trigger |
| `cooldown` | int (0-30) | Pause between launches in seconds |
| `czulosc_nn` | float (0.05-0.50) | Neural network confidence threshold (lower = more sensitive) |
| `slowa_kluczowe` | string | Voice commands separated by commas (empty = disabled) |
| `jezyk_mowy` | string | Speech recognition language: `pl` or `en` |

---

## Additional scripts

| File | Description |
|------|-------------|
| `clap-trigger.py` | Standalone clap trigger (simple, no neural network) |
| `voice-trigger.py` | Standalone voice trigger (Google Speech Recognition) |
| `workspace-launcher.ps1` | PowerShell launcher (independent of Python) |
| `workspace-hotkey.ahk` | AutoHotkey v2 shortcuts (`Ctrl+Alt+W`, `Ctrl+Alt+P`) |
| `create-shortcut.vbs` | Creates Windows startup shortcut |
| `build.bat` | Compiles .exe using PyInstaller |

### Standalone clap trigger

```bash
# Listen for double clap
python clap-trigger.py

# Calibration mode — check microphone level
python clap-trigger.py --calibrate

# Change threshold and profile
python clap-trigger.py --threshold 65 --profile praca --debug
```

---

## Building .exe

```bash
# Install PyInstaller
pip install pyinstaller

# Build WorkspaceLauncher.exe (console)
pyinstaller --onefile --name WorkspaceLauncher --console workspace.py

# Build WorkspaceConfig.exe (no console)
pyinstaller --onefile --name WorkspaceConfig --windowed config_gui.py
```

Or use the ready-made script:

```bash
build.bat
```

---

## Project structure

```
workspace-launcher/
├── workspace.py              # Main application (tray + detection + launcher)
├── config_gui.py             # Configuration GUI
├── clap-trigger.py           # Standalone clap trigger
├── voice-trigger.py          # Standalone voice trigger
├── workspace-launcher.ps1    # PowerShell launcher
├── workspace-hotkey.ahk      # AutoHotkey v2 shortcuts
├── workspace-config.json     # Configuration (created by GUI)
├── workspace-config.example.json  # Example configuration
├── build.bat                 # Build script for .exe
├── create-shortcut.vbs       # Startup shortcut creation
├── create-startup-shortcut.ps1
├── clap-trigger-startup.bat
├── requirements.txt          # Python dependencies
└── .gitignore
```

---

## License

MIT
