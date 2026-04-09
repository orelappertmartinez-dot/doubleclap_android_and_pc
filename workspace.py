"""
Workspace Launcher
System tray: clap detection + hotkey -> launches workspace -> stays in tray.
"""

import ctypes, ctypes.wintypes, json, math, os, queue, re, shutil, subprocess, sys, time, threading
from concurrent.futures import ThreadPoolExecutor
import numpy as np, sounddevice as sd

user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

# Properly define SetWindowPos argtypes for 64-bit HWND compatibility
user32.SetWindowPos.argtypes = [
    ctypes.wintypes.HWND, ctypes.wintypes.HWND,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_uint,
]
user32.SetWindowPos.restype = ctypes.wintypes.BOOL
user32.MoveWindow.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.wintypes.BOOL,
]
user32.MoveWindow.restype = ctypes.wintypes.BOOL
BASE_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "workspace-config.json")

HWND_TOP = ctypes.wintypes.HWND(0)
HWND_BOTTOM = ctypes.wintypes.HWND(1)
HWND_TOPMOST = ctypes.wintypes.HWND(-1 & 0xFFFFFFFFFFFFFFFF)  # proper 64-bit HWND
launched_pids = []
_pids_lock = threading.Lock()

def _add_pid(pid):
    with _pids_lock:
        launched_pids.append(pid)

# ── Win32 ─────────────────────────────────────────────────────

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", ctypes.wintypes.DWORD)]

def get_monitors():
    mons = []
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HMONITOR, ctypes.wintypes.HDC, ctypes.POINTER(RECT), ctypes.wintypes.LPARAM)
    def cb(h, hdc, lprc, d):
        mi = MONITORINFO(); mi.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(h, ctypes.byref(mi)); w = mi.rcWork
        mons.append((w.left, w.top, w.right - w.left, w.bottom - w.top)); return True
    user32.EnumDisplayMonitors(None, None, CB(cb), 0); return mons

def find_window(pattern, timeout=12, include_hidden=False):
    deadline = time.time() + timeout
    while time.time() < deadline:
        hit = []
        def cb(hwnd, _):
            if not include_hidden and not user32.IsWindowVisible(hwnd):
                return True
            if user32.GetWindowTextLengthW(hwnd) > 0:
                buf = ctypes.create_unicode_buffer(256); user32.GetWindowTextW(hwnd, buf, 256)
                if re.search(pattern, buf.value, re.IGNORECASE): hit.append(hwnd); return False
            return True
        user32.EnumWindows(EnumWindowsProc(cb), 0)
        if hit: return hit[0]
        time.sleep(0.3)
    return None

def find_new_window(pattern, before_handles, timeout=8):
    """Find a window matching pattern that was NOT in before_handles (i.e. newly created)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        hit = []
        def cb(hwnd, _):
            if hwnd in before_handles:
                return True
            if user32.GetWindowTextLengthW(hwnd) > 0:
                buf = ctypes.create_unicode_buffer(256); user32.GetWindowTextW(hwnd, buf, 256)
                if re.search(pattern, buf.value, re.IGNORECASE): hit.append(hwnd); return False
            return True
        user32.EnumWindows(EnumWindowsProc(cb), 0)
        if hit: return hit[0]
        time.sleep(0.3)
    return None

def find_any_new_visible_window(before_handles, timeout=6):
    """Find ANY new visible window with a title, not in before_handles.
    Last-resort fallback when pattern matching fails."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        hit = []
        def cb(hwnd, _):
            if hwnd in before_handles: return True
            if not user32.IsWindowVisible(hwnd): return True
            if user32.GetWindowTextLengthW(hwnd) > 0:
                hit.append(hwnd); return False
            return True
        user32.EnumWindows(EnumWindowsProc(cb), 0)
        if hit: return hit[0]
        time.sleep(0.3)
    return None

def _get_pids_for_exe(exe_name):
    """Get all PIDs of processes with given exe name (exact match)."""
    target = exe_name.lower()
    pids = set()
    try:
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            parts = line.strip().split('","')
            if parts and parts[0].strip('"').lower() == target:
                try: pids.add(int(parts[1].strip('"')))
                except ValueError: pass
    except Exception: pass
    return pids

def find_window_by_process(exe_name, timeout=6):
    """Find a visible window owned by any process with given exe name."""
    pids = _get_pids_for_exe(exe_name)
    if not pids: return None
    deadline = time.time() + timeout
    while time.time() < deadline:
        best = None
        def cb(hwnd, _):
            nonlocal best
            if not user32.IsWindowVisible(hwnd): return True
            if user32.GetWindowTextLengthW(hwnd) == 0: return True
            wpid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
            if wpid.value in pids:
                best = hwnd; return False
            return True
        user32.EnumWindows(EnumWindowsProc(cb), 0)
        if best: return best
        time.sleep(0.3)
    return None

def find_new_window_by_process(exe_name, before_handles, timeout=10):
    """Find a NEW visible window (not in before_handles) owned by a process with given exe name.
    Combines snapshot diff + process ownership = no cross-matching between threads."""
    pids = _get_pids_for_exe(exe_name)
    if not pids: return None
    deadline = time.time() + timeout
    while time.time() < deadline:
        hit = None
        def cb(hwnd, _):
            nonlocal hit
            if hwnd in before_handles: return True
            if not user32.IsWindowVisible(hwnd): return True
            if user32.GetWindowTextLengthW(hwnd) == 0: return True
            wpid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
            if wpid.value in pids:
                hit = hwnd; return False
            return True
        user32.EnumWindows(EnumWindowsProc(cb), 0)
        if hit: return hit
        time.sleep(0.3)
    return None

def find_window_by_pid(pid, timeout=10):
    """Find a window owned by given process ID."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        hit = []
        def cb(hwnd, _):
            if user32.GetWindowTextLengthW(hwnd) > 0:
                wpid = ctypes.wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
                if wpid.value == pid:
                    hit.append(hwnd); return False
            return True
        user32.EnumWindows(EnumWindowsProc(cb), 0)
        if hit: return hit[0]
        time.sleep(0.3)
    return None

def get_z(w): return {"On top": HWND_TOPMOST, "Behind": HWND_BOTTOM, "Na wierzchu": HWND_TOPMOST, "Pod spodem": HWND_BOTTOM}.get(w, HWND_TOP)

def place_window(hwnd, screen, half="", warstwa="Normalnie"):
    if not hwnd or screen < 1: return
    mons = get_monitors()
    idx = min(screen - 1, len(mons) - 1)
    mx, my, mw, mh = mons[idx]
    log("place", f"mon{screen}({mx},{my} {mw}x{mh}) half='{half}' warstwa='{warstwa}' hwnd={hwnd}")
    # Restore from minimize/maximize
    user32.ShowWindow(hwnd, 9)   # SW_RESTORE
    time.sleep(0.1)
    user32.ShowWindow(hwnd, 1)   # SW_NORMAL
    time.sleep(0.1)
    user32.SetForegroundWindow(hwnd)
    # Calculate target position
    if half in ("lewa", "left"):
        x, y, w, h = mx, my, mw // 2, mh
        log("place", f"LEFT: pos=({x},{y}) size=({w}x{h})")
    elif half in ("prawa", "right"):
        x, y, w, h = mx + mw // 2, my, mw // 2, mh
        log("place", f"RIGHT: pos=({x},{y}) size=({w}x{h})")
    else:
        x, y, w, h = mx, my, mw, mh
        log("place", f"FULL: pos=({x},{y}) size=({w}x{h})")
    # MoveWindow is more reliable than SetWindowPos for positioning
    result = user32.MoveWindow(hwnd, x, y, w, h, True)
    log("place", f"MoveWindow result={result}")
    # Set z-order separately
    z = get_z(warstwa)
    SWP_NOMOVE = 0x0002; SWP_NOSIZE = 0x0001; SWP_SHOWWINDOW = 0x0040
    user32.SetWindowPos(hwnd, z, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    # Maximize only for full screen
    if not half:
        user32.ShowWindow(hwnd, 3)

def _detect_default_browser():
    """Detect the system's default browser via registry."""
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice")
        prog_id = winreg.QueryValueEx(key, "ProgId")[0]; key.Close()
        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\shell\\open\\command")
        cmd = winreg.QueryValueEx(key, "")[0]; key.Close()
        m = re.match(r'"([^"]+)"', cmd)
        if m and os.path.exists(m.group(1)): return m.group(1)
    except Exception: pass
    # Fallback: scan common locations
    for name in ("Google\\Chrome\\Application\\chrome.exe", "Microsoft\\Edge\\Application\\msedge.exe",
                 "Mozilla Firefox\\firefox.exe", "BraveSoftware\\Brave-Browser\\Application\\brave.exe"):
        for root in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
            p = os.path.join(root, name)
            if os.path.exists(p): return p
    return None

_cached_browser = None
def _find_browser():
    global _cached_browser
    if _cached_browser is None:
        _cached_browser = _detect_default_browser() or ""
    return _cached_browser or None

def _is_browser_exe(exe):
    """Check if exe looks like a browser (supports --new-window)."""
    low = os.path.basename(exe).lower() if exe else ""
    return low in ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
                   "vivaldi.exe", "opera.exe", "chromium.exe")

# ── Helpers ───────────────────────────────────────────────────

def is_process_running(exe_path):
    """Check if a process with exact exe name is running."""
    if not exe_path: return False
    target = os.path.basename(exe_path).lower()
    try:
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line: continue
            # CSV format: "name.exe","PID","Session","#","Mem"
            parts = line.split('","')
            if parts:
                proc_name = parts[0].strip('"').lower()
                if proc_name == target:
                    return True
        return False
    except Exception: return False

def get_active_profile(cfg):
    profiles = cfg.get("profile", {})
    if isinstance(profiles, dict) and profiles:
        active = cfg.get("profil_aktywny", "")
        return profiles.get(active, next(iter(profiles.values())))
    return cfg

def get_profile_names(cfg):
    p = cfg.get("profile", {})
    return list(p.keys()) if isinstance(p, dict) else []

# ── Launchers ─────────────────────────────────────────────────

def log(name, msg): print(f"  [{name}] {msg}", flush=True)

def _is_app_execution_alias(path):
    """Check if path is a 0-byte App Execution Alias (UWP reparse point)."""
    try:
        if not os.path.exists(path): return False
        attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
        return attrs != -1 and (attrs & 0x400) and os.path.getsize(path) == 0
    except Exception: return False

def _launch_uwp(exe_path, name):
    """Launch UWP/Store app. Fast path: direct Popen (doesn't hang on App Execution Aliases).
    Fallback: protocol URI. Last resort: PowerShell AppID discovery."""
    log(name, f"UWP launch: {os.path.basename(exe_path)}")

    # Method 1: subprocess.Popen on the exe directly — works for App Execution Aliases,
    # exits immediately with code 0 and the real app is launched by Windows infrastructure
    if os.path.exists(exe_path):
        log(name, "Popen on exe (App Execution Alias)")
        subprocess.Popen([exe_path])
        return

    # Method 2: protocol URI (fast, no PowerShell needed)
    base = os.path.basename(exe_path).lower().replace(".exe", "").replace("-", "")
    # Try to find a matching protocol in registry
    import winreg
    for proto in (base, base.replace("ms", "ms-", 1)):
        try:
            key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, proto)
            winreg.QueryValueEx(key, "URL Protocol"); key.Close()
            log(name, f"protocol URI: {proto}:")
            os.startfile(f"{proto}:")
            return
        except Exception: pass

    # Method 3: PowerShell AppID discovery (slow, last resort)
    hint = base.replace("'", "''")
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             f"(Get-AppxPackage | Where-Object {{$_.Name -like '*{hint}*'}} | Select-Object -First 1).PackageFamilyName"],
            capture_output=True, text=True, timeout=10, creationflags=0x08000000)
        pfn = r.stdout.strip().split('\n')[0].strip()
        if pfn:
            log(name, f"shell:AppsFolder\\{pfn}!App")
            subprocess.Popen(["cmd.exe", "/c", "start", "", f"shell:AppsFolder\\{pfn}!App"],
                              creationflags=0x08000000)
            return
    except Exception: pass

    log(name, f"fallback: start {os.path.basename(exe_path)}")
    subprocess.Popen(["cmd.exe", "/c", "start", "", os.path.basename(exe_path)],
                      creationflags=0x08000000)

def _build_pattern(name):
    """Build window-title regex from app name. Uses full name only — first-word
    fallback was too broad (e.g. 'Microsoft' matched Edge, Word, etc.)."""
    return re.escape(name)

def _resolve_exe(exe):
    """Resolve exe: returns (full_path_or_cmd, needs_shell).
    .cmd/.bat files need shell=True because they're scripts, not PE executables."""
    if not exe: return None, False
    def _needs_shell(path):
        return os.path.splitext(path)[1].lower() in ('.cmd', '.bat')
    if os.path.isabs(exe) and os.path.exists(exe):
        return exe, _needs_shell(exe)
    found = shutil.which(exe)
    if found: return found, _needs_shell(found)
    # Not found — assume it's a command name, needs shell
    return exe, True

def _url_to_app_uri(url):
    """Convert known app HTTPS URLs to native protocol URIs.
    e.g. https://open.spotify.com/track/xxx → spotify:track:xxx"""
    if not url: return None
    m = re.match(r'https?://open\.spotify\.com/(\w+)/([a-zA-Z0-9]+)', url)
    if m: return f"spotify:{m.group(1)}:{m.group(2)}"
    return None

def _launch_app_by_protocol(protocol, name):
    """Launch an app by its protocol name. Tries direct exe first (no browser redirect),
    falls back to protocol URI activation. Returns exe name if found, else None."""
    # Try to find the app's exe in WindowsApps (most reliable, no browser redirect)
    wa_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps")
    if os.path.isdir(wa_dir):
        for f in os.listdir(wa_dir):
            if f.lower().startswith(protocol.lower()) and f.lower().endswith(".exe"):
                exe_path = os.path.join(wa_dir, f)
                if os.path.exists(exe_path):
                    log(name, f"direct start: {f}")
                    subprocess.Popen([exe_path])
                    return f.lower()
    # Try desktop install (e.g. Spotify in APPDATA)
    if protocol.lower() == "spotify":
        sp = os.path.join(os.environ.get("APPDATA", ""), "Spotify", "Spotify.exe")
        if os.path.isfile(sp) and os.path.getsize(sp) > 0:
            log(name, f"desktop exe: {sp}")
            subprocess.Popen([sp])
            return "spotify.exe"
    return None

def _launch_process(exe, args_str, name):
    """Launch a process. Returns (proc, is_new, effective_exe_name).
    effective_exe_name is the actual process name for window finding."""
    is_url = args_str.startswith("http") if args_str else False
    is_uwp = exe and "windowsapps" in exe.lower()
    is_browser = exe and _is_browser_exe(exe)
    already_running = exe and is_process_running(exe)
    eff_exe = os.path.basename(exe).lower() if exe else ""

    # ── Convert known app URLs to native protocol URIs (e.g. spotify:track:xxx) ──
    app_uri = _url_to_app_uri(args_str) if is_url else None
    if app_uri:
        protocol = app_uri.split(":")[0]
        log(name, f"URL -> app URI: {app_uri}")
        launched_exe = _launch_app_by_protocol(protocol, name)
        time.sleep(3)
        log(name, f"sending URI: {app_uri}")
        os.startfile(app_uri)
        return None, True, launched_exe or ""

    # ── Protocol URIs (spotify:, msteams:, etc.) — not HTTP URLs ──
    if not exe and args_str and not is_url:
        protocol = args_str.split(":")[0]
        launched_exe = _launch_app_by_protocol(protocol, name)
        time.sleep(2)
        os.startfile(args_str)
        return None, True, launched_exe or ""

    # ── UWP app (Teams, Calculator, etc.) ──
    if is_uwp:
        if already_running:
            log(name, "UWP already running - activating")
        else:
            log(name, "UWP - launching")
        _launch_uwp(exe, name)
        time.sleep(2)
        return None, not already_running, eff_exe

    # ── Browser with URL — always open new window ──
    if is_browser and is_url:
        resolved, _ = _resolve_exe(exe)
        browser = resolved if resolved and os.path.exists(resolved) else _find_browser()
        b_exe = os.path.basename(browser).lower() if browser else eff_exe
        if browser:
            log(name, f"new browser window: {args_str}")
            proc = subprocess.Popen([browser, "--new-window", args_str])
            _add_pid(proc.pid)
            return proc, True, b_exe
        log(name, "browser not found, fallback os.startfile")
        os.startfile(args_str)
        return None, True, b_exe

    # ── Empty exe + URL — use default browser ──
    if not exe and is_url:
        browser = _find_browser()
        b_exe = os.path.basename(browser).lower() if browser else ""
        if browser:
            log(name, f"default browser new window: {args_str}")
            proc = subprocess.Popen([browser, "--new-window", args_str])
            _add_pid(proc.pid)
            return proc, True, b_exe
        os.startfile(args_str)
        return None, True, b_exe

    # ── Already running non-browser app with args — new instance ──
    if already_running and args_str:
        log(name, f"already running, new instance with args")
        resolved, needs_shell = _resolve_exe(exe)
        proc = subprocess.Popen([resolved] + args_str.split(), shell=needs_shell)
        _add_pid(proc.pid)
        return proc, True, eff_exe

    # ── Already running non-browser app without args — just reposition ──
    if already_running:
        log(name, "already running - looking for window to reposition")
        return None, False, eff_exe

    # ── Fresh launch ──
    resolved, needs_shell = _resolve_exe(exe)
    if not resolved:
        log(name, "cannot launch - exe not found"); return None, False, eff_exe

    log(name, f"start: {resolved}")
    if args_str:
        proc = subprocess.Popen([resolved] + args_str.split(), shell=needs_shell)
    else:
        proc = subprocess.Popen([resolved], shell=needs_shell)
    _add_pid(proc.pid)

    # Spotify: play specific track/URI after launch
    if args_str and "spotify" in args_str.lower():
        m = re.search(r"(track|album|artist|playlist)[/:]([a-zA-Z0-9]+)", args_str)
        if m:
            uri = f"spotify:{m.group(1)}:{m.group(2)}"
            time.sleep(3); os.startfile(uri); log(name, f"playing: {uri}")
        elif args_str.startswith("spotify:"):
            time.sleep(3); os.startfile(args_str); log(name, "playing")

    return proc, True, eff_exe

def launch_app(app):
    """Launch a single app and position its window according to config."""
    name = app.get("nazwa", "app")
    exe = app.get("exe", "")
    args_str = app.get("argumenty", "").strip()
    ekran = app.get("ekran", 0)
    polowa = app.get("polowa", "")
    warstwa = app.get("warstwa", "Normalnie")
    minimalizuj = app.get("minimalizuj", False)

    if not exe and not args_str:
        log(name, "skipped"); return

    # Snapshot existing windows BEFORE launch
    before = _get_all_window_handles()
    pattern = _build_pattern(name)

    try:
        proc, is_new, effective_exe = _launch_process(exe, args_str, name)

        if not (ekran > 0 or minimalizuj):
            log(name, "ok"); return

        # ── Resolve exe name for process-based search ──
        exe_for_search = effective_exe
        if exe_for_search and not exe_for_search.endswith(".exe"):
            exe_for_search += ".exe"

        time.sleep(2 if is_new else 0.3)
        hwnd = None

        if is_new:
            # For NEW windows: find new window owned by OUR process (prevents cross-matching)
            if exe_for_search:
                log(name, f"looking for new window of process {exe_for_search}...")
                hwnd = find_new_window_by_process(exe_for_search, before, timeout=10)
            # Fallback: any new visible window (if we don't know the process)
            if not hwnd:
                log(name, f"looking for any new window...")
                hwnd = find_any_new_visible_window(before, timeout=6)
        else:
            # For ALREADY RUNNING apps: find by process ownership
            if exe_for_search:
                log(name, f"looking for window of process {exe_for_search}...")
                hwnd = find_window_by_process(exe_for_search, timeout=4)
            if not hwnd:
                log(name, f"looking for window by pattern '{pattern}'...")
                hwnd = find_window(pattern, timeout=4, include_hidden=True)

        # Universal fallback: find by PID
        if not hwnd and proc:
            log(name, f"looking for window by PID {proc.pid}...")
            hwnd = find_window_by_pid(proc.pid, timeout=4)

        if hwnd:
            log(name, f"found hwnd={hwnd}")
            if ekran > 0: place_window(hwnd, ekran, polowa, warstwa)
            if minimalizuj: user32.ShowWindow(hwnd, 6)
        else:
            log(name, f"window NOT found")

        log(name, "ok")
    except Exception as e:
        log(name, f"ERROR: {e}")

def _get_all_window_handles():
    """Get set of all current window handles."""
    handles = set()
    def cb(hwnd, _):
        handles.add(hwnd); return True
    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return handles

def launch_terminal(term):
    name = term.get("nazwa", "Terminal")
    typ = term.get("terminal_typ", "Git Bash")
    folder = term.get("folder", os.path.expanduser("~"))
    komenda = term.get("komenda", "")
    ekran = term.get("ekran", 0)
    polowa = term.get("polowa", "")
    warstwa = term.get("warstwa", "Normalnie")
    log(name, f"{typ}: {komenda.split(chr(10))[0] if komenda else '(shell)'}")

    # Snapshot all windows BEFORE launching so we can find the NEW one
    before_handles = _get_all_window_handles()

    proc = None
    try:
        if typ == "Git Bash":
            # Detect Git installation dynamically
            import winreg as _wr
            git_dir = None
            for _rk in (_wr.HKEY_LOCAL_MACHINE, _wr.HKEY_CURRENT_USER):
                try:
                    _k = _wr.OpenKey(_rk, r"Software\GitForWindows")
                    git_dir = _wr.QueryValueEx(_k, "InstallPath")[0]; _k.Close(); break
                except Exception: pass
            if not git_dir:
                git_exe = shutil.which("git")
                if git_exe: git_dir = os.path.dirname(os.path.dirname(git_exe))
            if not git_dir: git_dir = os.path.join(os.environ.get("ProgramFiles", ""), "Git")
            mintty = os.path.join(git_dir, "usr", "bin", "mintty.exe")
            bash = os.path.join(git_dir, "bin", "bash.exe")
            if not os.path.exists(bash): log(name, "Git Bash not found"); return
            posix = folder.replace("\\", "/")
            if len(posix) >= 2 and posix[1] == ":": posix = "/" + posix[0].lower() + posix[2:]
            s = os.path.join(BASE_DIR, f"_term_{name.replace(' ','_')}.sh")
            with open(s, "w", newline="\n") as f:
                f.write(f'cd "{posix}"\n'); komenda and f.write(komenda+"\n"); f.write('exec bash --login\n')
            if os.path.exists(mintty):
                # mintty creates a proper Win32 window (SetWindowPos works)
                proc = subprocess.Popen([mintty, f"--title={name}", "-e", "/bin/bash", "--login", s])
            else:
                proc = subprocess.Popen([bash, "--login", s], creationflags=0x10)
        elif typ == "PowerShell":
            s = os.path.join(BASE_DIR, f"_term_{name.replace(' ','_')}.ps1")
            with open(s, "w", encoding="utf-8") as f:
                f.write(f'Set-Location "{folder}"\n'); komenda and f.write(komenda+"\n")
            proc = subprocess.Popen(["powershell.exe","-NoExit","-ExecutionPolicy","Bypass","-File",s], creationflags=0x10)
        elif typ == "CMD":
            s = os.path.join(BASE_DIR, f"_term_{name.replace(' ','_')}.bat")
            with open(s, "w", encoding="utf-8") as f:
                f.write(f'@cd /d "{folder}"\n'); komenda and f.write(komenda+"\n")
            proc = subprocess.Popen(["cmd.exe","/k",s], creationflags=0x10)
        elif typ == "Windows Terminal":
            proc = subprocess.Popen(["wt.exe","new-tab","-d",folder])

        if proc: _add_pid(proc.pid)

        if ekran > 0:
            hwnd = None
            # Strategy 1: find by title (mintty sets --title=name)
            log(name, f"looking for window by title '{name}'...")
            time.sleep(2)
            hwnd = find_window(re.escape(name), timeout=10)
            # Strategy 2: find by PID (works for mintty, wt.exe)
            if not hwnd and proc:
                log(name, f"looking for window by PID {proc.pid}...")
                hwnd = find_window_by_pid(proc.pid, timeout=8)
            # Strategy 3: find new window by snapshot diff
            if not hwnd:
                log(name, "looking for new window (snapshot)...")
                after_handles = _get_all_window_handles()
                for h in (after_handles - before_handles):
                    if user32.IsWindowVisible(h) and user32.GetWindowTextLengthW(h) > 0:
                        hwnd = h; break
            if hwnd:
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buf, 256)
                log(name, f"found: '{buf.value}' (hwnd={hwnd})")
                # Apply position, wait for app to initialize, re-apply
                # (mintty/claude can reposition the window during startup)
                place_window(hwnd, ekran, polowa, warstwa)
                time.sleep(3)
                place_window(hwnd, ekran, polowa, warstwa)
                log(name, f"position applied 2x")
            else:
                log(name, f"terminal window NOT found")
        log(name, "ok")
    except Exception as e:
        log(name, f"ERROR: {e}")

def launch_profile(data):
    global launched_pids
    with _pids_lock:
        launched_pids = []
    apps = data.get("aplikacje", []); terms = data.get("terminale", [])
    print(f"\n{'='*40}\n  LAUNCHING WORKSPACE\n{'='*40}\n", flush=True)

    # Phase 1: launch apps with explicit order (kolejnosc > 0) — sequentially
    ordered = {}
    rest = []
    for a in apps:
        k = a.get("kolejnosc", 0)
        if k > 0:
            ordered.setdefault(k, []).append(a)
        else:
            rest.append(a)
    for k in sorted(ordered.keys()):
        for a in ordered[k]: launch_app(a)

    # Phase 2: launch remaining apps
    # Group by executable basename — same exe runs SEQUENTIALLY (prevents window cross-matching)
    # Different exes run in PARALLEL (fast startup)
    exe_groups = {}
    for a in rest:
        key = os.path.basename(a.get("exe", "") or "").lower()
        if not key:
            args = a.get("argumenty", "")
            if args.startswith("http"):
                # URL-only entries open in default browser — group with same browser exe
                browser = _find_browser()
                key = os.path.basename(browser).lower() if browser else "_url_"
            else:
                key = "_other_"
        exe_groups.setdefault(key, []).append(a)

    def _launch_group(group_apps):
        """Launch a group of apps with same exe SEQUENTIALLY."""
        for a in group_apps:
            launch_app(a)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(_launch_group, group) for group in exe_groups.values()]
        futs += [pool.submit(launch_terminal, t) for t in terms]
        for f in futs:
            try: f.result()
            except Exception as e: print(f"  ! {e}", flush=True)
    print(f"\n{'='*40}\n  DONE! ({len(launched_pids)} processes)\n{'='*40}\n", flush=True)

def close_workspace():
    closed = 0
    for pid in launched_pids:
        try: subprocess.run(["taskkill","/F","/PID",str(pid),"/T"], capture_output=True, timeout=5); closed += 1
        except: pass
    launched_pids.clear()
    print(f"  Closed {closed} processes.", flush=True)

# ── Clap detection (PANNs neural network) ─────────────────────

CLAP_THRESHOLD_SCORE = 0.12  # PANNs confidence threshold (configurable via czulosc_nn)
TRIGGER_COUNT = 2  # how many events to trigger (overridden by config)
TRIGGER_COOLDOWN = 3.0  # seconds between workspace launches (overridden by config)

# Related sound groups - selecting one catches acoustically similar sounds
TRIGGER_GROUPS = {
    "Clapping":        {"Clapping", "Finger snapping", "Hands", "Slap, smack", "Cap gun"},
    "Finger snapping": {"Finger snapping", "Clapping", "Hands", "Snap"},
    "Whistling":       {"Whistling", "Whistle"},
    "Knock":           {"Knock", "Door", "Tap"},
    "Slap, smack":     {"Slap, smack", "Clapping", "Hands"},
    "Bell":            {"Bell", "Bicycle bell", "Church bell"},
    "Doorbell":        {"Doorbell", "Bell", "Ding-dong"},
    "Snap":            {"Snap", "Finger snapping", "Clapping"},
}
TRIGGER_LABELS = {"Clapping", "Finger snapping", "Hands", "Slap, smack", "Cap gun"}  # default

_panns_model = None
_panns_lock = threading.Lock()
_panns_ready = threading.Event()

def get_panns():
    global _panns_model
    with _panns_lock:
        if _panns_model is None:
            # Model file - check local dir first, then user home
            model_name = "Cnn14_mAP=0.431.pth"
            local_model = os.path.join(BASE_DIR, model_name)
            home_model = os.path.join(os.path.expanduser("~"), "panns_data", model_name)
            model_path = local_model if os.path.exists(local_model) else (home_model if os.path.exists(home_model) else None)

            if not model_path:
                print("  Downloading sound recognition model (~80MB, one-time)...", flush=True)
                os.makedirs(os.path.dirname(home_model), exist_ok=True)
                import urllib.request
                urllib.request.urlretrieve(
                    "https://zenodo.org/record/3987831/files/Cnn14_mAP%3D0.431.pth", home_model)
                model_path = home_model
                print("  Model downloaded.", flush=True)

            from panns_inference import AudioTagging
            _panns_model = AudioTagging(checkpoint_path=model_path, device='cpu')
            _panns_ready.set()
            print("  PANNs CNN14 loaded.", flush=True)
    return _panns_model

def preload_panns():
    """Load model in background - doesn't block app startup."""
    threading.Thread(target=get_panns, daemon=True).start()

_audioset_labels = None

def get_audioset_labels():
    global _audioset_labels
    if _audioset_labels is None:
        try:
            from panns_inference.config import labels
            _audioset_labels = labels
        except Exception:
            _audioset_labels = []
    return _audioset_labels

def rms_db(data):
    rms = np.sqrt(np.mean(data.astype(np.float64) ** 2))
    return max(0.0, 20 * math.log10(rms) + 96) if rms > 1e-10 else 0.0

def classify_audio(audio_buffer):
    """Uses PANNs CNN14 to classify audio. Returns (is_trigger, trigger_score, top_label_str)."""
    try:
        at = get_panns()
        ratio = 32000 / 44100
        resampled = np.interp(
            np.linspace(0, len(audio_buffer), int(len(audio_buffer) * ratio)),
            np.arange(len(audio_buffer)),
            audio_buffer.astype(np.float32)
        )
        audio_in = resampled.reshape(1, -1).astype(np.float32)
        scores, _ = at.inference(audio_in)

        labels = get_audioset_labels()

        # Top predicted label
        top_i = int(np.argmax(scores[0]))
        top_name = labels[top_i] if labels and top_i < len(labels) else f"#{top_i}"
        top_score = float(scores[0][top_i])

        # Find best trigger score among ALL labels (no index lookup needed)
        trigger_score = 0.0
        if labels:
            for i, name in enumerate(labels):
                if name in TRIGGER_LABELS and scores[0][i] > trigger_score:
                    trigger_score = float(scores[0][i])
        else:
            # Fallback: just use top label match
            trigger_score = top_score if top_name in TRIGGER_LABELS else 0.0

        is_trigger = trigger_score > CLAP_THRESHOLD_SCORE
        return is_trigger, trigger_score, f"{top_name} ({top_score:.2f})"
    except Exception as e:
        return False, 0.0, f"ERR: {e}"

def meter_print(msg):
    """Print a message clearing the volume meter line first."""
    sys.stdout.write("\r" + " " * 100 + "\r")
    print(msg, flush=True)

def wait_for_claps(threshold, callback=None):
    """Listens for impulsive sounds (claps/snaps). Counting is instant (crest factor),
    NN only verifies AFTER the count is reached — no queue delays."""
    RATE = 44100; BLOCK = 4096
    NN_WINDOW = RATE // 2
    state = {
        "prev_db": 0.0, "spike_times": [], "running": True,
        "audio_buf": np.zeros(RATE, dtype=np.float32), "buf_pos": 0,
        "current_db": 0.0, "last_sound": "", "error": "",
        "last_trigger": 0.0, "verify_at": 0,
    }
    inference_q = queue.Queue(maxsize=2)

    preload_panns()

    def safe_callback(n):
        try:
            callback(n)
        except Exception as e:
            meter_print(f"  ! ERROR launching workspace: {e}")
            import traceback; traceback.print_exc()

    # NN verification worker — only runs AFTER count is reached
    def inference_worker():
        while state["running"]:
            try:
                audio_snap, db, now = inference_q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                is_trigger, score, top_label = classify_audio(audio_snap)
                if top_label:
                    state["last_sound"] = top_label
                if is_trigger:
                    cooldown_left = TRIGGER_COOLDOWN - (time.time() - state["last_trigger"])
                    if cooldown_left > 0:
                        meter_print(f"  [!] Cooldown: {cooldown_left:.0f}s remaining")
                    else:
                        meter_print(f"  >>> NN confirms: {top_label} (score: {score:.2f}) — launching!")
                        state["last_trigger"] = time.time()
                        if callback:
                            threading.Thread(target=safe_callback, args=(0,), daemon=True).start()
                else:
                    meter_print(f"  [x] NN rejected: {top_label} (score: {score:.2f})")
            except Exception as e:
                meter_print(f"  ! ERROR inference: {e}")
    threading.Thread(target=inference_worker, daemon=True).start()

    # Live volume meter display thread
    def display_loop():
        while state["running"]:
            db = state["current_db"]
            model_ok = _panns_ready.is_set()
            last = state["last_sound"]
            err = state["error"]

            bar_w = 30
            filled = int(min(db / 96.0, 1.0) * bar_w)
            thresh_pos = min(int(threshold / 96.0 * bar_w), bar_w - 1)

            bar = ""
            for i in range(bar_w):
                if i == thresh_pos and i >= filled:
                    bar += "!"
                elif i < filled:
                    bar += "|"
                else:
                    bar += "."

            nn = "OK" if model_ok else "loading..."
            line = f"\r  MIC [{bar}] {db:4.0f}/{threshold} dB | NN: {nn}"
            if err:
                line += f" | ERR: {err}"
            elif last:
                line += f" | {last}"
            line += "    "

            sys.stdout.write(line)
            sys.stdout.flush()
            time.sleep(0.15)
    threading.Thread(target=display_loop, daemon=True).start()

    def cb(indata, frames, t, status):
        if not state["running"]: return
        if status:
            state["error"] = str(status)
        elif state["error"]:
            state["error"] = ""
        try:
            samples = indata[:, 0]
            db = rms_db(samples)
            state["current_db"] = db
            now = time.time()

            # Accumulate audio buffer (rolling 1s window)
            buf = state["audio_buf"]
            n = len(samples)
            buf[:-n] = buf[n:]
            buf[-n:] = samples
            state["buf_pos"] += n

            # Rising edge + crest factor → instant spike counting (no NN needed)
            if db >= threshold and state["prev_db"] < threshold and state["buf_pos"] >= RATE:
                peak = float(np.max(np.abs(samples)))
                rms_val = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
                crest = peak / rms_val if rms_val > 1e-10 else 0
                if crest >= 4.0:
                    state["spike_times"] = [st for st in state["spike_times"] if now - st < 2.0] + [now]
                    nc = len(state["spike_times"])
                    meter_print(f"  [{'*'*nc}] Spike #{nc}/{TRIGGER_COUNT} ({db:.0f} dB, crest: {crest:.1f})")
                    if nc >= TRIGGER_COUNT and (TRIGGER_COUNT < 2 or state["spike_times"][-1] - state["spike_times"][-2] >= 0.08):
                        state["spike_times"] = []
                        # Schedule NN verification (delayed capture for better audio)
                        state["verify_at"] = state["buf_pos"] + BLOCK

            # Delayed NN verification — only after spike count reached
            if state["verify_at"] > 0 and state["buf_pos"] >= state["verify_at"]:
                nn_buf = buf[-NN_WINDOW:].copy()
                try: inference_q.put_nowait((nn_buf, db, now))
                except queue.Full: pass
                state["verify_at"] = 0

            # Feed audio to Vosk voice trigger (shared stream, no separate mic)
            vf = state.get("voice_feed")
            if vf:
                try: vf(samples)
                except: pass

            state["prev_db"] = db
        except Exception as e:
            state["error"] = str(e)

    stream = sd.InputStream(samplerate=RATE, blocksize=BLOCK, channels=1, callback=cb)
    stream.start()
    return stream, state

# ── Voice trigger (Vosk) ─────────────────────────────────────

VOSK_MODELS = {
    "pl": ("vosk-model-small-pl-0.22", "https://alphacephei.com/vosk/models/vosk-model-small-pl-0.22.zip"),
    "en": ("vosk-model-small-en-us-0.15", "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"),
}

def _fix_vosk_dll():
    """Fix vosk DLL loading in PyInstaller --onefile builds."""
    if not getattr(sys, 'frozen', False):
        return
    try:
        import shutil
        meipass = getattr(sys, '_MEIPASS', '')
        vosk_dir = os.path.join(meipass, 'vosk')
        os.makedirs(vosk_dir, exist_ok=True)
        for dll in ['libvosk.dll', 'libgcc_s_seh-1.dll', 'libstdc++-6.dll', 'libwinpthread-1.dll']:
            src = os.path.join(meipass, dll)
            dst = os.path.join(vosk_dir, dll)
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
    except Exception as e:
        meter_print(f"  ! Fix vosk DLL: {e}")

def get_vosk_model(lang):
    """Download and load Vosk model for given language."""
    if lang not in VOSK_MODELS:
        meter_print(f"  ! Unknown language: {lang}, available: {', '.join(VOSK_MODELS.keys())}")
        return None
    model_name, url = VOSK_MODELS[lang]
    model_dir = os.path.join(os.path.expanduser("~"), "vosk_models", model_name)
    if not os.path.isdir(model_dir):
        zip_path = model_dir + ".zip"
        meter_print(f"  Downloading speech model ({lang}, ~50MB)...")
        os.makedirs(os.path.dirname(model_dir), exist_ok=True)
        import urllib.request, zipfile
        urllib.request.urlretrieve(url, zip_path)
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(os.path.dirname(model_dir))
        try: os.remove(zip_path)
        except: pass
        meter_print(f"  Speech model ({lang}) downloaded.")
    _fix_vosk_dll()
    meter_print(f"  Loading speech model ({lang})...")
    from vosk import Model, SetLogLevel
    SetLogLevel(-1)
    model = Model(model_dir)
    meter_print(f"  Speech model ({lang}) ready.")
    return model

def start_voice_trigger(keywords, lang, cooldown_ref, callback):
    """Listen for voice keywords using Vosk. Fed from shared audio stream (no separate mic)."""
    state = {"running": True, "last_trigger": 0.0, "last_text": "", "rec": None, "ready": False}
    kw_list = [k.strip().lower() for k in keywords.split(",") if k.strip()]
    if not kw_list:
        meter_print("  ! No keywords for speech recognition")
        return state

    def init_vosk():
        try:
            model = get_vosk_model(lang)
            if not model:
                return
            from vosk import KaldiRecognizer
            state["rec"] = KaldiRecognizer(model, 16000)
            state["ready"] = True
            meter_print(f"  Keywords active: {', '.join(kw_list)} ({lang})")
        except Exception as e:
            meter_print(f"  ! Vosk failed: {e} — voice commands disabled")
    threading.Thread(target=init_vosk, daemon=True).start()

    audio_q = queue.Queue(maxsize=30)

    def voice_worker():
        """Downsample + Vosk processing in separate thread (not in audio callback)."""
        while state["running"]:
            rec = state.get("rec")
            if not rec:
                time.sleep(0.5)
                continue
            try:
                samples = audio_q.get(timeout=0.5)
            except queue.Empty:
                try:
                    result = rec.Result()
                    if result:
                        _check_keywords(result)
                except: pass
                continue
            try:
                ratio = 16000 / 44100
                n_out = int(len(samples) * ratio)
                downsampled = np.interp(
                    np.linspace(0, len(samples), n_out),
                    np.arange(len(samples)),
                    samples
                )
                pcm = (downsampled * 32767).astype(np.int16).tobytes()
                rec.AcceptWaveform(pcm)
                result = rec.PartialResult()
                if result:
                    text = json.loads(result).get("partial", "").lower()
                    if text:
                        for kw in kw_list:
                            if kw in text:
                                final = rec.FinalResult()
                                _check_keywords(final)
                                break
            except Exception:
                pass

    def _check_keywords(result_json):
        text = json.loads(result_json).get("text", "").lower() if isinstance(result_json, str) else ""
        if not text:
            return
        state["last_text"] = text
        for kw in kw_list:
            if kw in text:
                now = time.time()
                cd = cooldown_ref[0] - (now - state["last_trigger"])
                if cd > 0:
                    meter_print(f"  [mic] \"{text}\" — cooldown: {cd:.0f}s")
                else:
                    meter_print(f"  >>> Voice command: \"{text}\" (keyword: {kw})")
                    state["last_trigger"] = now
                    threading.Thread(target=callback, daemon=True).start()
                break

    threading.Thread(target=voice_worker, daemon=True).start()

    def feed_audio(samples_44100):
        """Called from audio callback — just queues samples, no heavy processing."""
        if not state.get("ready"):
            return
        try:
            audio_q.put_nowait(samples_44100.copy())
        except queue.Full:
            pass

    state["feed"] = feed_audio
    return state

# ── Hotkey ────────────────────────────────────────────────────

MODIFIER_MAP = {"Ctrl": 0x0002, "Alt": 0x0001, "Shift": 0x0004, "Win": 0x0008}
VK_MAP = {chr(c): c for c in range(0x41, 0x5B)}  # A-Z
VK_MAP.update({str(i): 0x30+i for i in range(10)})  # 0-9
VK_MAP.update({"F"+str(i): 0x6F+i for i in range(1,13)})  # F1-F12
VK_MAP.update({"Space": 0x20, "Enter": 0x0D, "Tab": 0x09})

def parse_hotkey(hotkey_str):
    """Parse 'Win+Shift+W' -> (modifiers, vk)"""
    parts = [p.strip() for p in hotkey_str.split("+")]
    mods = 0; vk = 0
    for p in parts:
        if p in MODIFIER_MAP:
            mods |= MODIFIER_MAP[p]
        elif p.upper() in VK_MAP:
            vk = VK_MAP[p.upper()]
    return mods, vk

def register_hotkey(hotkey_str, callback, hotkey_id=1):
    mods, vk = parse_hotkey(hotkey_str)
    if not vk:
        print(f"  ! Invalid hotkey: {hotkey_str}", flush=True)
        return None

    WM_HOTKEY = 0x0312
    def thread():
        user32.RegisterHotKey(None, hotkey_id, mods, vk)
        msg = ctypes.wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY and msg.wParam == hotkey_id:
                callback()
    t = threading.Thread(target=thread, daemon=True); t.start()
    return t

# ── Tray ──────────────────────────────────────────────────────

def create_tray(cfg, on_launch, on_close, on_config, on_quit):
    import pystray
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, 56, 56], fill=(46, 204, 113))
    d.ellipse([22, 22, 42, 42], fill=(255, 255, 255))

    names = get_profile_names(cfg)
    items = []
    if names:
        for n in names:
            items.append(pystray.MenuItem(f"Launch: {n}", lambda _, n=n: on_launch(n)))
        items.append(pystray.Menu.SEPARATOR)
    else:
        items.append(pystray.MenuItem("Launch workspace", lambda: on_launch(None)))
        items.append(pystray.Menu.SEPARATOR)

    items += [
        pystray.MenuItem("Close workspace", lambda: on_close()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Configuration", lambda: on_config()),
        pystray.MenuItem("Quit", lambda: on_quit()),
    ]
    return pystray.Icon("WorkspaceLauncher", img, "Workspace Launcher", pystray.Menu(*items))

# ── Main ──────────────────────────────────────────────────────

def main():
    if not os.path.exists(CONFIG_PATH):
        ce = os.path.join(BASE_DIR, "WorkspaceConfig.exe")
        if os.path.exists(ce): os.startfile(ce)
        else: print("Missing workspace-config.json!")
        input("Enter..."); sys.exit(0)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f: cfg = json.load(f)

    global CLAP_THRESHOLD_SCORE, TRIGGER_LABELS, TRIGGER_COUNT, TRIGGER_COOLDOWN
    threshold = cfg.get("czulosc_klasniecia", 70)
    CLAP_THRESHOLD_SCORE = cfg.get("czulosc_nn", CLAP_THRESHOLD_SCORE)
    trigger_sound = cfg.get("zdarzenie_dzwiekowe", "Clapping")
    TRIGGER_LABELS = TRIGGER_GROUPS.get(trigger_sound, {trigger_sound})
    TRIGGER_COUNT = cfg.get("liczba_zdarzen", 2)
    TRIGGER_COOLDOWN = cfg.get("cooldown", 3)
    hotkey_str = cfg.get("hotkey", "Win+Shift+W")
    profile = get_active_profile(cfg)
    apps = profile.get("aplikacje", []); terms = profile.get("terminale", [])
    if not apps and not terms: print("No apps configured!"); input("Enter..."); sys.exit(0)

    pnames = get_profile_names(cfg)
    print(f"{'='*40}\n  Workspace Launcher\n{'='*40}")
    print(f"  Sensitivity: {threshold} dB | NN threshold: {CLAP_THRESHOLD_SCORE} | Hotkey: {hotkey_str}")
    print(f"  Trigger: {trigger_sound} x{TRIGGER_COUNT} | Cooldown: {TRIGGER_COOLDOWN}s")
    if pnames: print(f"  Profiles: {', '.join(pnames)} | Active: {cfg.get('profil_aktywny', pnames[0])}")
    print(f"  Apps: {len(apps)} | Terminals: {len(terms)}")
    print(f"  Detection: spectral analysis (distinguishes claps from speech/music)")
    print(f"{'-'*40}", flush=True)

    # List monitors
    mons = get_monitors()
    print(f"  Monitors ({len(mons)}):", flush=True)
    for i, (mx, my, mw, mh) in enumerate(mons):
        print(f"    [{i+1}] pos=({mx},{my}) size={mw}x{mh}", flush=True)

    # List audio input devices for debugging
    print("  Audio devices (input):", flush=True)
    try:
        devices = sd.query_devices()
        default_in = sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else sd.default.device
        found_any = False
        for i, d in enumerate(devices):
            if d['max_input_channels'] > 0:
                marker = " <<< ACTIVE" if i == default_in else ""
                print(f"    [{i}] {d['name']} (ch:{d['max_input_channels']}, {int(d['default_samplerate'])}Hz){marker}", flush=True)
                found_any = True
        if not found_any:
            print("    ! No input devices - microphone will not be detected!", flush=True)
    except Exception as e:
        print(f"    ! Error listing devices: {e}", flush=True)
    print(f"{'-'*40}", flush=True)

    lock = threading.Lock()
    def do_launch(name=None):
        with lock:
            data = cfg["profile"][name] if name and name in cfg.get("profile", {}) else get_active_profile(cfg)
            meter_print(f"\n  >>> Profile: {name or 'default'}")
            launch_profile(data)
    def do_close(): meter_print("  >>> Closing..."); close_workspace()
    def do_config():
        ce = os.path.join(BASE_DIR, "WorkspaceConfig.exe")
        if os.path.exists(ce): os.startfile(ce)

    # Voice trigger (optional) — init AFTER audio stream to not block startup
    voice_state = None
    voice_feed = None
    voice_keywords = cfg.get("slowa_kluczowe", "").strip()
    voice_lang = cfg.get("jezyk_mowy", "en")
    cooldown_ref = [TRIGGER_COOLDOWN]

    stream, clap_state = wait_for_claps(threshold, callback=lambda n: do_launch())
    print("  Listening... (bar below shows microphone level)", flush=True)

    register_hotkey(hotkey_str, lambda: do_launch())
    print(f"  Hotkey {hotkey_str} registered.", flush=True)

    # Voice trigger — started AFTER everything else so crash doesn't block startup
    if voice_keywords:
        print(f"  Voice command: \"{voice_keywords}\" ({voice_lang}) — loading in background...", flush=True)
        voice_state = start_voice_trigger(voice_keywords, voice_lang, cooldown_ref, lambda: do_launch())
        # Connect voice feed to existing audio stream
        def _voice_feeder(samples):
            f = voice_state.get("feed")
            if f: f(samples)
        clap_state["voice_feed"] = _voice_feeder
    else:
        print("  Voice command: disabled", flush=True)

    tray = [None]
    def on_quit():
        clap_state["running"] = False; stream.stop()
        if voice_state: voice_state["running"] = False
        if tray[0]: tray[0].stop()
    tray[0] = create_tray(cfg, do_launch, do_close, do_config, on_quit)
    print("  Tray icon active.\n", flush=True)
    tray[0].run()

if __name__ == "__main__": main()
