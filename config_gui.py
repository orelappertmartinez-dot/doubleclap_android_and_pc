"""Workspace Launcher - Configuration"""

import ctypes, ctypes.wintypes, json, os, shutil, subprocess, sys, winreg
import customtkinter as ctk
from tkinter import filedialog, messagebox

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BASE_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "workspace-config.json")

# ── System helpers ────────────────────────────────────────────

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", ctypes.wintypes.DWORD)]

def get_monitors():
    mons = []
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HMONITOR, ctypes.wintypes.HDC, ctypes.POINTER(RECT), ctypes.wintypes.LPARAM)
    def cb(h, hdc, lprc, d):
        mi = MONITORINFO(); mi.cbSize = ctypes.sizeof(MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(h, ctypes.byref(mi)); w = mi.rcWork
        mons.append((w.left, w.top, w.right - w.left, w.bottom - w.top)); return True
    ctypes.windll.user32.EnumDisplayMonitors(None, None, CB(cb), 0); return mons

def scan_installed_apps():
    """Scan for all installed apps using registry, Start Menu, UWP, and Program Files."""
    apps = {}  # name -> exe path
    seen_exes = set()  # lowercase exe paths for dedup

    SKIP_NAMES = ["update", "uninstall", "odinstal", "redistributable", "runtime",
                  "driver", "sdk", "library", ".net", "visual c++", "readme",
                  "help", "license", "migration", "repair", "setup"]
    SKIP_UWP = ["framework", "runtime", "vclibs", "net.native", "windowsappruntime",
                "appinstaller", "designtime", "hosting", "ui.xaml", "winjs",
                "services.store", "extension", "d3d", "media."]

    def _should_skip(name):
        lo = name.lower()
        return any(s in lo for s in SKIP_NAMES)

    def _add(name, exe):
        if not name or not exe:
            return
        key = exe.lower()
        if key in seen_exes:
            return
        if _should_skip(name):
            return
        seen_exes.add(key)
        apps[name] = exe

    # ── Method 1: Windows Registry ──
    reg_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, subkey in reg_keys:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                i = 0
                while True:
                    try:
                        sub_name = winreg.EnumKey(key, i)
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(key, sub_name) as sk:
                            try:
                                display_name = winreg.QueryValueEx(sk, "DisplayName")[0]
                            except OSError:
                                continue
                            if _should_skip(display_name):
                                continue
                            # Try InstallLocation first, then DisplayIcon
                            exe_path = None
                            try:
                                loc = winreg.QueryValueEx(sk, "InstallLocation")[0]
                                if loc and os.path.isdir(loc):
                                    # Look for exe matching the folder name or common patterns
                                    for candidate in os.listdir(loc):
                                        if candidate.lower().endswith(".exe"):
                                            clo = candidate.lower()
                                            if clo not in ("unins000.exe", "uninstall.exe", "update.exe", "setup.exe"):
                                                exe_path = os.path.join(loc, candidate)
                                                break
                            except OSError:
                                pass
                            if not exe_path:
                                try:
                                    icon = winreg.QueryValueEx(sk, "DisplayIcon")[0]
                                    # DisplayIcon can be "path.exe" or "path.exe,0"
                                    icon = icon.split(",")[0].strip().strip('"')
                                    if icon.lower().endswith(".exe") and os.path.exists(icon):
                                        exe_path = icon
                                except OSError:
                                    pass
                            if exe_path:
                                _add(display_name, exe_path)
                    except OSError:
                        continue
        except OSError:
            continue

    # ── Method 2: Start Menu shortcuts (VBScript) ──
    lnk_files = []
    for d in [os.path.join(os.environ.get("PROGRAMDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
              os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")]:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.lower().endswith(".lnk"):
                    lnk_files.append(os.path.join(root, f))
    if lnk_files:
        vbs, out = os.path.join(BASE_DIR, "_r.vbs"), os.path.join(BASE_DIR, "_a.txt")
        lines = ['Set sh=CreateObject("WScript.Shell")',
                 f'Set f=CreateObject("Scripting.FileSystemObject").CreateTextFile("{out}",True,True)']
        for lnk in lnk_files:
            n = os.path.splitext(os.path.basename(lnk))[0].replace('"', '""')
            lines += ['On Error Resume Next',
                      f'Set s=sh.CreateShortcut("{lnk.replace(chr(34), "")}")',
                      f'If Err.Number=0 Then f.WriteLine "{n}" & vbTab & s.TargetPath',
                      'On Error GoTo 0']
        lines.append('f.Close')
        with open(vbs, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        try:
            subprocess.run(["cscript", "//nologo", vbs], timeout=15, capture_output=True)
        except Exception:
            pass
        if os.path.exists(out):
            try:
                with open(out, "r", encoding="utf-16") as f:
                    for line in f:
                        p = line.strip().split("\t", 1)
                        if len(p) == 2 and p[1] and p[1].lower().endswith(".exe"):
                            _add(p[0], p[1])
            except Exception:
                pass
        for p in [vbs, out]:
            try:
                os.remove(p)
            except Exception:
                pass

    # ── Method 3: UWP / Store apps via PowerShell ──
    try:
        ps_cmd = (
            'Get-AppxPackage | Where-Object {$_.IsFramework -eq $false -and $_.SignatureKind -ne "System"} '
            '| Select-Object Name, InstallLocation | ConvertTo-Csv -NoTypeInformation'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode == 0:
            csv_lines = result.stdout.strip().splitlines()
            for row in csv_lines[1:]:  # skip header
                # CSV: "Name","InstallLocation"
                parts = row.strip('"').split('","')
                if len(parts) >= 2:
                    pkg_name = parts[0].strip('"')
                    pkg_loc = parts[1].strip('"')
                    # Skip framework-like packages
                    if any(s in pkg_name.lower() for s in SKIP_UWP):
                        continue
                    # Derive a display name from the package name
                    # e.g. "Microsoft.WindowsCalculator" -> "Windows Calculator"
                    short = pkg_name.split(".")[-1] if "." in pkg_name else pkg_name
                    # Insert spaces before capitals: "WindowsCalculator" -> "Windows Calculator"
                    display = ""
                    for ch in short:
                        if ch.isupper() and display and not display.endswith(" "):
                            display += " "
                        display += ch
                    if display and pkg_loc:
                        # Use shell:AppsFolder launch protocol
                        _add(display, f"shell:AppsFolder\\{pkg_name}!App")
    except Exception:
        pass

    # ── Method 4: Scan Program Files directories ──
    SKIP_DIRS = {"windows", "microsoft sdks", "microsoft.net", "reference assemblies",
                 "windows defender", "windows mail", "windows media player",
                 "windows nt", "windows photo viewer", "windows portable devices",
                 "windows sidebar", "windowspowershell", "common files", "uninstall information",
                 "msbuild", "iis", "internet explorer", "package cache"}
    for env_var in ("ProgramFiles", "ProgramFiles(x86)"):
        prog_dir = os.environ.get(env_var, "")
        if not prog_dir or not os.path.isdir(prog_dir):
            continue
        try:
            entries = os.listdir(prog_dir)
        except OSError:
            continue
        for entry in entries:
            if entry.lower() in SKIP_DIRS:
                continue
            full = os.path.join(prog_dir, entry)
            if not os.path.isdir(full):
                continue
            # Look for exe in root of dir
            best_exe = None
            try:
                for f in os.listdir(full):
                    if not f.lower().endswith(".exe"):
                        continue
                    flo = f.lower()
                    if flo in ("unins000.exe", "uninstall.exe", "update.exe", "setup.exe", "updater.exe"):
                        continue
                    candidate = os.path.join(full, f)
                    # Prefer exe whose name matches the directory name
                    if os.path.splitext(f)[0].lower() == entry.lower():
                        best_exe = candidate
                        break
                    if best_exe is None:
                        best_exe = candidate
            except OSError:
                pass
            # Also check bin/ subfolder
            if not best_exe:
                bin_dir = os.path.join(full, "bin")
                if os.path.isdir(bin_dir):
                    try:
                        for f in os.listdir(bin_dir):
                            if f.lower().endswith(".exe") and f.lower() not in ("uninstall.exe", "update.exe"):
                                best_exe = os.path.join(bin_dir, f)
                                break
                    except OSError:
                        pass
            if best_exe:
                _add(entry, best_exe)

    # ── Method 4b: Git Bash via registry or PATH ──
    if "Git Bash" not in apps:
        git_bash_exe = None
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\GitForWindows") as gk:
                git_install = winreg.QueryValueEx(gk, "InstallPath")[0]
                candidate = os.path.join(git_install, "git-bash.exe")
                if os.path.exists(candidate):
                    git_bash_exe = candidate
        except OSError:
            pass
        if not git_bash_exe:
            found = shutil.which("git-bash") or shutil.which("git-bash.exe")
            if found:
                git_bash_exe = found
        if git_bash_exe:
            _add("Git Bash", git_bash_exe)

    return sorted([{"name": k, "exe": v} for k, v in apps.items()], key=lambda x: x["name"].lower())

# ── Picker dialog ─────────────────────────────────────────────

def pick_app(parent, apps):
    result = [None]
    dlg = ctk.CTkToplevel(parent)
    dlg.title("Add application")
    dlg.geometry("520x550")
    dlg.transient(parent)
    dlg.grab_set()
    dlg.after(10, dlg.focus_force)

    ctk.CTkLabel(dlg, text="Choose application", font=("Segoe UI", 18, "bold")).pack(padx=20, pady=(20, 5), anchor="w")
    ctk.CTkLabel(dlg, text="Search the list or browse for .exe", text_color="#888").pack(padx=20, anchor="w")

    sv = ctk.StringVar()
    search = ctk.CTkEntry(dlg, textvariable=sv, placeholder_text="Search...", height=36)
    search.pack(fill="x", padx=20, pady=(12, 8))
    search.focus_set()

    list_frame = ctk.CTkFrame(dlg, fg_color="transparent")
    list_frame.pack(fill="both", expand=True, padx=20)

    # Use tkinter Listbox inside CTk frame for scrollable list
    import tkinter as tk
    lb_frame = ctk.CTkFrame(list_frame, fg_color="#2b2b2b", corner_radius=8)
    lb_frame.pack(fill="both", expand=True)
    sb = tk.Scrollbar(lb_frame)
    sb.pack(side="right", fill="y", padx=(0, 2), pady=4)
    lb = tk.Listbox(lb_frame, font=("Segoe UI", 11), bg="#2b2b2b", fg="#ddd",
                     selectbackground="#1f6aa5", selectforeground="#fff",
                     borderwidth=0, highlightthickness=0, yscrollcommand=sb.set)
    lb.pack(fill="both", expand=True, padx=(8, 0), pady=4)
    sb.config(command=lb.yview)

    filtered = list(apps)
    def upd(*_):
        nonlocal filtered
        q = sv.get().lower()
        filtered = [a for a in apps if q in a["name"].lower()] if q else list(apps)
        lb.delete(0, "end")
        for a in filtered: lb.insert("end", a["name"])
    sv.trace_add("write", upd); upd()

    btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
    btn_frame.pack(fill="x", padx=20, pady=(12, 20))

    def sel():
        s = lb.curselection()
        if s: result[0] = filtered[s[0]]; dlg.destroy()
    def brw():
        p = filedialog.askopenfilename(parent=dlg, filetypes=[("Exe", "*.exe"), ("All", "*.*")])
        if p: result[0] = {"name": os.path.splitext(os.path.basename(p))[0], "exe": p}; dlg.destroy()

    ctk.CTkButton(btn_frame, text="Browse .exe...", command=brw, fg_color="#444", hover_color="#555", width=140).pack(side="left")
    ctk.CTkButton(btn_frame, text="Add", command=sel, width=120).pack(side="right")
    lb.bind("<Double-1>", lambda e: sel())

    dlg.wait_window()
    return result[0]

# ── Welcome dialog ────────────────────────────────────────────

APP_DESCRIPTION = (
    "Workspace Launcher opens your work environment on a double clap. "
    "Add apps and terminals, set which screen they should open on, "
    "save and run WorkspaceLauncher.exe."
)

def show_welcome(parent):
    dlg = ctk.CTkToplevel(parent)
    dlg.title("Welcome!")
    dlg.geometry("520x420")
    dlg.transient(parent)
    dlg.grab_set()
    dlg.after(10, dlg.focus_force)

    content = ctk.CTkFrame(dlg, fg_color="transparent")
    content.pack(fill="both", expand=True, padx=30, pady=25)

    ctk.CTkLabel(content, text="Workspace Launcher", font=("Segoe UI", 22, "bold")).pack(anchor="w")
    ctk.CTkLabel(content, text="v1.0", text_color="#666").pack(anchor="w", pady=(0, 15))
    ctk.CTkLabel(content, text=APP_DESCRIPTION, wraplength=440, justify="left", text_color="#bbb").pack(anchor="w", pady=(0, 20))

    ctk.CTkLabel(content, text="Getting started", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 8))
    steps = [
        "1.  Click  + Add application  and pick from the list",
        "2.  Set screen, position and layer",
        "3.  Add terminals in the Terminals tab",
        "4.  Save and run WorkspaceLauncher.exe",
        "5.  Clap 2x — everything will launch",
    ]
    for s in steps:
        ctk.CTkLabel(content, text=s, text_color="#999", anchor="w").pack(anchor="w", pady=1)

    ctk.CTkButton(content, text="Let's go!", command=dlg.destroy, height=38, font=("Segoe UI", 13)).pack(pady=(20, 0))
    dlg.wait_window()

# ── Main GUI ──────────────────────────────────────────────────

WARSTWY = ["Normal", "On top", "Behind"]
TERM_TYPES = ["Git Bash", "PowerShell", "CMD", "Windows Terminal"]

def main():
    mons = get_monitors(); mc = max(len(mons), 1)
    cfg = {"czulosc_klasniecia": 70, "aplikacje": [], "terminale": []}
    first_run = not os.path.exists(CONFIG_PATH)
    if not first_run:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f: cfg = json.load(f)
    installed = scan_installed_apps()

    root = ctk.CTk()
    root.title("Workspace Launcher")
    root.geometry("740x680")
    root.minsize(680, 450)

    # ── Header ──
    header = ctk.CTkFrame(root, fg_color="transparent")
    header.pack(fill="x", padx=24, pady=(20, 0))
    ctk.CTkLabel(header, text="Workspace Launcher", font=("Segoe UI", 22, "bold")).pack(side="left")
    ctk.CTkLabel(header, text=f"{len(mons)} screens  ·  {len(installed)} apps",
                 text_color="#666").pack(side="right")

    ctk.CTkLabel(root, text=APP_DESCRIPTION, wraplength=680, text_color="#777",
                 font=("Segoe UI", 11)).pack(padx=24, pady=(4, 12), anchor="w")

    if first_run:
        root.after(200, lambda: show_welcome(root))

    # ── Profile selector ──
    profiles = cfg.get("profile", {})
    profile_names = list(profiles.keys()) if isinstance(profiles, dict) else []
    active_name = cfg.get("profil_aktywny", "")

    # If old flat config, wrap it
    if not profile_names:
        active_name = "Default"
        profile_names = [active_name]
        profiles = {active_name: {"aplikacje": cfg.get("aplikacje", []), "terminale": cfg.get("terminale", [])}}

    if active_name not in profile_names: active_name = profile_names[0]

    prof_bar = ctk.CTkFrame(root, fg_color="transparent")
    prof_bar.pack(fill="x", padx=24, pady=(0, 8))
    ctk.CTkLabel(prof_bar, text="Profile:", font=("Segoe UI", 12)).pack(side="left", padx=(0, 8))

    current_profile = {"name": active_name, "data": profiles}

    prof_var = ctk.StringVar(value=active_name)
    prof_menu = ctk.CTkOptionMenu(prof_bar, variable=prof_var, values=profile_names, width=180, height=32,
                                    command=lambda v: switch_profile(v))
    prof_menu.pack(side="left", padx=(0, 8))

    def add_profile():
        dlg = ctk.CTkInputDialog(text="New profile name:", title="New profile")
        name = dlg.get_input()
        if not name or name in current_profile["data"]: return
        current_profile["data"][name] = {"aplikacje": [], "terminale": []}
        profile_names.append(name)
        prof_menu.configure(values=profile_names)
        prof_var.set(name)
        switch_profile(name)

    def delete_profile():
        name = prof_var.get()
        if len(profile_names) <= 1:
            messagebox.showwarning("Profile", "Cannot delete the last profile."); return
        if not messagebox.askyesno("Profile", f"Delete profile '{name}'?"): return
        save_current_to_profile()
        del current_profile["data"][name]
        profile_names.remove(name)
        prof_menu.configure(values=profile_names)
        prof_var.set(profile_names[0])
        switch_profile(profile_names[0])

    ctk.CTkButton(prof_bar, text="+", width=32, height=32, command=add_profile).pack(side="left", padx=2)
    ctk.CTkButton(prof_bar, text="✕", width=32, height=32, fg_color="#c0392b", hover_color="#e74c3c",
                   command=delete_profile).pack(side="left", padx=2)

    # ── Bottom bar (packed FIRST at bottom so it's always visible) ──
    bottom = ctk.CTkFrame(root, fg_color="transparent")
    bottom.pack(side="bottom", fill="x", padx=20, pady=(5, 15))

    # ── Tabs ──
    tabs = ctk.CTkTabview(root, corner_radius=10)
    tabs.pack(fill="both", expand=True, padx=20, pady=(0, 5))
    tab_apps = tabs.add("Apps")
    tab_term = tabs.add("Terminals")
    tab_set = tabs.add("Settings")

    # ═══════════ TAB: Aplikacje ═══════════
    app_scroll = ctk.CTkScrollableFrame(tab_apps, fg_color="transparent")
    app_scroll.pack(fill="both", expand=True)
    app_cards = []

    def add_app(data=None):
        if data is None: data = {}
        card = ctk.CTkFrame(app_scroll, corner_radius=10)
        card.pack(fill="x", pady=4, padx=2)
        w = {"frame": card}

        # Row 1: name + exe type + flags + delete
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 0))

        nv = ctk.StringVar(value=data.get("nazwa", ""))
        ctk.CTkEntry(top, textvariable=nv, font=("Segoe UI", 13), width=200, height=32).pack(side="left")
        w["nazwa"] = nv

        exe_val = data.get("exe", "")
        w["exe"] = ctk.StringVar(value=exe_val)
        exe_name = os.path.basename(exe_val) if exe_val else "not selected"
        ctk.CTkLabel(top, text=exe_name, text_color="#666", font=("Segoe UI", 11)).pack(side="left", padx=(10, 0))

        def rm(): card.destroy(); app_cards.remove(w)
        ctk.CTkButton(top, text="✕", width=32, height=32, fg_color="#c0392b", hover_color="#e74c3c",
                       font=("Segoe UI", 14), command=rm).pack(side="right")

        mini = ctk.BooleanVar(value=data.get("minimalizuj", False))
        ctk.CTkCheckBox(top, text="Minimize", variable=mini, width=20).pack(side="right", padx=(0, 8))
        w["minimalizuj"] = mini

        ctk.CTkLabel(top, text="Order", text_color="#888").pack(side="right", padx=(0, 4))
        ov = ctk.IntVar(value=data.get("kolejnosc", 0))
        ctk.CTkEntry(top, textvariable=ov, width=40, height=32).pack(side="right", padx=(0, 8))
        w["kolejnosc"] = ov

        # Row 2: arguments
        r2 = ctk.CTkFrame(card, fg_color="transparent")
        r2.pack(fill="x", padx=12, pady=(6, 0))
        ctk.CTkLabel(r2, text="Arguments (optional)", text_color="#888", font=("Segoe UI", 11)).pack(side="left", padx=(0, 6))
        av = ctk.StringVar(value=data.get("argumenty", ""))
        ctk.CTkEntry(r2, textvariable=av, height=30,
                      placeholder_text="URL, folder or file path...").pack(side="left", fill="x", expand=True, padx=(0, 4))
        def make_picker(v):
            def pk():
                d = filedialog.askdirectory()
                if d: v.set(d)
            return pk
        ctk.CTkButton(r2, text="...", width=36, height=30, fg_color="#444", hover_color="#555",
                       command=make_picker(av)).pack(side="left")
        w["argumenty"] = av

        ctk.CTkLabel(card, text="Browser: page URL  ·  VS Code: project folder  ·  Spotify: track link  ·  Other: leave empty",
                      text_color="#555", font=("Segoe UI", 10)).pack(padx=12, anchor="w", pady=(2, 0))

        # Row 3: screen + position + layer
        r3 = ctk.CTkFrame(card, fg_color="transparent")
        r3.pack(fill="x", padx=12, pady=(6, 10))

        ctk.CTkLabel(r3, text="Screen", text_color="#888").pack(side="left", padx=(0, 4))
        ev = ctk.IntVar(value=data.get("ekran", 1))
        ctk.CTkEntry(r3, textvariable=ev, width=45, height=30).pack(side="left", padx=(0, 12))
        w["ekran"] = ev

        ctk.CTkLabel(r3, text="Position", text_color="#888").pack(side="left", padx=(0, 4))
        pv = ctk.StringVar(value=data.get("polowa", "") or "full")
        ctk.CTkOptionMenu(r3, variable=pv, values=["full", "left", "right"], width=100, height=30).pack(side="left", padx=(0, 12))
        w["polowa"] = pv

        ctk.CTkLabel(r3, text="Layer", text_color="#888").pack(side="left", padx=(0, 4))
        zv = ctk.StringVar(value=data.get("warstwa", "Normal"))
        ctk.CTkOptionMenu(r3, variable=zv, values=WARSTWY, width=120, height=30).pack(side="left")
        w["warstwa"] = zv

        app_cards.append(w)

    # Load active profile apps
    active_data = profiles.get(active_name, {})
    for a in active_data.get("aplikacje", []): add_app(a)

    def save_current_to_profile():
        """Save current cards state into profile data."""
        apps = []
        for w in app_cards:
            apps.append({
                "nazwa": w["nazwa"].get(), "exe": w["exe"].get(),
                "argumenty": w["argumenty"].get(), "ekran": w["ekran"].get(),
                "polowa": w["polowa"].get() if w["polowa"].get() != "full" else "",
                "warstwa": w["warstwa"].get(), "kolejnosc": w["kolejnosc"].get(),
                "minimalizuj": w["minimalizuj"].get(),
            })
        terms = []
        for t in term_cards:
            komenda = t["komenda_widget"].get("1.0", "end").strip()
            terms.append({
                "nazwa": t["nazwa"].get(), "terminal_typ": t["terminal_typ"].get(),
                "folder": t["folder"].get(), "komenda": komenda,
                "ekran": t["ekran"].get(), "polowa": t["polowa"].get() if t["polowa"].get() != "full" else "",
                "warstwa": t["warstwa"].get(),
            })
        current_profile["data"][current_profile["name"]] = {"aplikacje": apps, "terminale": terms}

    def switch_profile(new_name):
        save_current_to_profile()
        current_profile["name"] = new_name
        # Clear all cards
        for w in list(app_cards): w["frame"].destroy()
        app_cards.clear()
        for w in list(term_cards): w["frame"].destroy()
        term_cards.clear()
        # Remove any leftover separators
        for child in app_scroll.winfo_children():
            if isinstance(child, ctk.CTkFrame) or str(child).endswith("separator"):
                child.destroy()
        # Load new profile
        data = current_profile["data"].get(new_name, {})
        for a in data.get("aplikacje", []): add_app(a)
        for t in data.get("terminale", []): add_term(t)

    def on_add():
        picked = pick_app(root, installed)
        if not picked: return
        add_app({"nazwa": picked["name"], "exe": picked["exe"], "ekran": 1})

    # ═══════════ TAB: Terminale ═══════════
    ctk.CTkLabel(tab_term, text="Open terminal in selected folder and run command",
                 text_color="#888").pack(anchor="w", padx=8, pady=(5, 10))

    term_scroll = ctk.CTkScrollableFrame(tab_term, fg_color="transparent")
    term_scroll.pack(fill="both", expand=True)
    term_cards = []

    def add_term(data=None):
        if data is None: data = {}
        card = ctk.CTkFrame(term_scroll, corner_radius=10)
        card.pack(fill="x", pady=4, padx=2)
        tw = {"frame": card}

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 0))
        nv = ctk.StringVar(value=data.get("nazwa", "Terminal"))
        ctk.CTkEntry(top, textvariable=nv, font=("Segoe UI", 13), width=180, height=32).pack(side="left")
        tw["nazwa"] = nv

        ctk.CTkLabel(top, text="Typ", text_color="#888").pack(side="left", padx=(12, 4))
        tv = ctk.StringVar(value=data.get("terminal_typ", "Git Bash"))
        ctk.CTkOptionMenu(top, variable=tv, values=TERM_TYPES, width=150, height=30).pack(side="left")
        tw["terminal_typ"] = tv

        def rm(): card.destroy(); term_cards.remove(tw)
        ctk.CTkButton(top, text="✕", width=32, height=32, fg_color="#c0392b", hover_color="#e74c3c",
                       font=("Segoe UI", 14), command=rm).pack(side="right")

        r2 = ctk.CTkFrame(card, fg_color="transparent")
        r2.pack(fill="x", padx=12, pady=(6, 0))
        ctk.CTkLabel(r2, text="Folder", text_color="#888").pack(side="left", padx=(0, 6))
        fv = ctk.StringVar(value=data.get("folder", ""))
        ctk.CTkEntry(r2, textvariable=fv, height=30).pack(side="left", fill="x", expand=True, padx=(0, 4))
        def make_picker(v):
            def pk():
                d = filedialog.askdirectory()
                if d: v.set(d)
            return pk
        ctk.CTkButton(r2, text="...", width=36, height=30, fg_color="#444", hover_color="#555",
                       command=make_picker(fv)).pack(side="left")
        tw["folder"] = fv

        # Row 3: script/command (textarea)
        r3 = ctk.CTkFrame(card, fg_color="transparent")
        r3.pack(fill="x", padx=12, pady=(6, 0))
        ctk.CTkLabel(r3, text="Script / Command", text_color="#888").pack(anchor="w", pady=(0, 4))
        cmd_text = ctk.CTkTextbox(r3, height=60, font=("Consolas", 12), corner_radius=6)
        cmd_text.pack(fill="x")
        cmd_text.insert("1.0", data.get("komenda", ""))
        tw["komenda_widget"] = cmd_text

        # Row 4: screen + position + layer
        r4 = ctk.CTkFrame(card, fg_color="transparent")
        r4.pack(fill="x", padx=12, pady=(6, 10))

        ctk.CTkLabel(r4, text="Screen", text_color="#888").pack(side="left", padx=(0, 4))
        ev = ctk.IntVar(value=data.get("ekran", 1))
        ctk.CTkEntry(r4, textvariable=ev, width=45, height=30).pack(side="left", padx=(0, 12))
        tw["ekran"] = ev

        ctk.CTkLabel(r4, text="Position", text_color="#888").pack(side="left", padx=(0, 4))
        pv = ctk.StringVar(value=data.get("polowa", "") or "full")
        ctk.CTkOptionMenu(r4, variable=pv, values=["full", "left", "right"], width=100, height=30).pack(side="left", padx=(0, 12))
        tw["polowa"] = pv

        ctk.CTkLabel(r4, text="Layer", text_color="#888").pack(side="left", padx=(0, 4))
        zv = ctk.StringVar(value=data.get("warstwa", "Normal"))
        ctk.CTkOptionMenu(r4, variable=zv, values=WARSTWY, width=120, height=30).pack(side="left")
        tw["warstwa"] = zv

        term_cards.append(tw)

    for t in active_data.get("terminale", []): add_term(t)

    ctk.CTkButton(tab_term, text="+ Add terminal", command=add_term, width=160, height=36,
                   fg_color="#444", hover_color="#555").pack(anchor="w", padx=8, pady=(10, 0))

    # ═══════════ TAB: Ustawienia ═══════════
    set_scroll = ctk.CTkScrollableFrame(tab_set, fg_color="transparent")
    set_scroll.pack(fill="both", expand=True)

    set_frame = ctk.CTkFrame(set_scroll, corner_radius=10)
    set_frame.pack(fill="x", padx=8, pady=(8, 12))

    ctk.CTkLabel(set_frame, text="Clap sensitivity", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=16, pady=(12, 0))
    ctk.CTkLabel(set_frame, text="Lower value = easier to detect claps. Default: 70 dB.",
                 text_color="#888").pack(anchor="w", padx=16, pady=(2, 8))

    slider_frame = ctk.CTkFrame(set_frame, fg_color="transparent")
    slider_frame.pack(fill="x", padx=16, pady=(0, 12))
    ctk.CTkLabel(slider_frame, text="40", text_color="#888").pack(side="left")
    czulosc = ctk.IntVar(value=cfg.get("czulosc_klasniecia", 70))
    czulosc_label = ctk.CTkLabel(slider_frame, text=str(czulosc.get()), font=("Segoe UI", 16, "bold"), width=40)
    czulosc_label.pack(side="right", padx=(8, 0))
    ctk.CTkLabel(slider_frame, text="dB", text_color="#888").pack(side="right")
    ctk.CTkLabel(slider_frame, text="95", text_color="#888").pack(side="right", padx=(0, 8))
    def on_slider(val):
        iv = int(float(val)); czulosc.set(iv); czulosc_label.configure(text=str(iv))
    ctk.CTkSlider(slider_frame, from_=40, to=95, variable=czulosc, command=on_slider,
                   number_of_steps=55).pack(side="left", fill="x", expand=True, padx=8)

    # Hotkey
    hk_frame = ctk.CTkFrame(set_scroll, corner_radius=10)
    hk_frame.pack(fill="x", padx=8, pady=(0, 8))
    ctk.CTkLabel(hk_frame, text="Keyboard shortcut", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=16, pady=(12, 0))
    ctk.CTkLabel(hk_frame, text="Alternative to claps. Key combination to launch workspace.",
                 text_color="#888").pack(anchor="w", padx=16, pady=(2, 8))
    hk_row = ctk.CTkFrame(hk_frame, fg_color="transparent")
    hk_row.pack(fill="x", padx=16, pady=(0, 12))
    hotkey_var = ctk.StringVar(value=cfg.get("hotkey", "Win+Shift+W"))
    ctk.CTkEntry(hk_row, textvariable=hotkey_var, width=200, height=32,
                  placeholder_text="e.g. Win+Shift+W, Ctrl+Alt+S").pack(side="left")
    ctk.CTkLabel(hk_row, text="Available: Ctrl, Alt, Shift, Win + letter/digit/F1-F12",
                 text_color="#666").pack(side="left", padx=(12, 0))

    # ── Sound trigger settings ──
    trigger_frame = ctk.CTkFrame(set_scroll, corner_radius=10)
    trigger_frame.pack(fill="x", padx=8, pady=(0, 8))

    ctk.CTkLabel(trigger_frame, text="Sound trigger", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=16, pady=(12, 0))
    ctk.CTkLabel(trigger_frame, text="Choose the sound that triggers workspace, repeat count, and cooldown between launches.",
                 text_color="#888").pack(anchor="w", padx=16, pady=(2, 8))

    TRIGGER_OPTIONS = ["Clapping", "Finger snapping", "Whistling", "Knock", "Slap, smack", "Bell", "Doorbell", "Snap"]

    tr1 = ctk.CTkFrame(trigger_frame, fg_color="transparent")
    tr1.pack(fill="x", padx=16, pady=(0, 6))
    ctk.CTkLabel(tr1, text="Sound:", text_color="#888").pack(side="left", padx=(0, 8))
    trigger_var = ctk.StringVar(value=cfg.get("zdarzenie_dzwiekowe", "Clapping"))
    ctk.CTkOptionMenu(tr1, variable=trigger_var, values=TRIGGER_OPTIONS, width=200, height=32).pack(side="left")

    ctk.CTkLabel(tr1, text="Count:", text_color="#888").pack(side="left", padx=(20, 8))
    count_var = ctk.StringVar(value=str(cfg.get("liczba_zdarzen", 2)))
    ctk.CTkOptionMenu(tr1, variable=count_var, values=["1", "2", "3"], width=70, height=32).pack(side="left")
    ctk.CTkLabel(tr1, text="(in 1.5 sec)", text_color="#666").pack(side="left", padx=(8, 0))

    tr2 = ctk.CTkFrame(trigger_frame, fg_color="transparent")
    tr2.pack(fill="x", padx=16, pady=(0, 6))
    ctk.CTkLabel(tr2, text="Cooldown:", text_color="#888").pack(side="left", padx=(0, 8))
    cooldown_var = ctk.IntVar(value=cfg.get("cooldown", 3))
    cd_label = ctk.CTkLabel(tr2, text=f"{cooldown_var.get()} sec", font=("Segoe UI", 13, "bold"), width=50)
    cd_label.pack(side="right")
    def on_cd(val):
        iv = int(float(val)); cooldown_var.set(iv); cd_label.configure(text=f"{iv} sec")
    ctk.CTkSlider(tr2, from_=0, to=30, variable=cooldown_var, command=on_cd,
                   number_of_steps=30).pack(side="left", fill="x", expand=True, padx=8)

    tr3 = ctk.CTkFrame(trigger_frame, fg_color="transparent")
    tr3.pack(fill="x", padx=16, pady=(0, 12))
    ctk.CTkLabel(tr3, text="NN sensitivity:", text_color="#888").pack(side="left", padx=(0, 8))
    nn_var = ctk.DoubleVar(value=cfg.get("czulosc_nn", 0.12))
    nn_label = ctk.CTkLabel(tr3, text=f"{nn_var.get():.2f}", font=("Segoe UI", 13, "bold"), width=50)
    nn_label.pack(side="right")
    def on_nn(val):
        fv = round(float(val), 2); nn_var.set(fv); nn_label.configure(text=f"{fv:.2f}")
    ctk.CTkSlider(tr3, from_=0.05, to=0.50, variable=nn_var, command=on_nn,
                   number_of_steps=45).pack(side="left", fill="x", expand=True, padx=8)
    ctk.CTkLabel(trigger_frame, text="Lower = easier detection (more false positives). Higher = harder (fewer errors).",
                 text_color="#666", font=("Segoe UI", 10)).pack(anchor="w", padx=16, pady=(0, 12))

    auto_frame = ctk.CTkFrame(set_scroll, corner_radius=10)
    auto_frame.pack(fill="x", padx=8, pady=(0, 8))
    auto_var = ctk.BooleanVar(value=os.path.exists(
        os.path.join(os.environ.get("APPDATA",""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "WorkspaceLauncher.lnk")))
    ctk.CTkCheckBox(auto_frame, text="Start automatically with Windows",
                     variable=auto_var).pack(padx=16, pady=12, anchor="w")
    ctk.CTkLabel(auto_frame, text="WorkspaceLauncher.exe waits in background (tray icon) for clap or hotkey Win+Shift+W.",
                 text_color="#888").pack(padx=16, pady=(0, 12), anchor="w")

    # ── Voice trigger settings ──
    voice_frame = ctk.CTkFrame(set_scroll, corner_radius=10)
    voice_frame.pack(fill="x", padx=8, pady=(0, 8))

    ctk.CTkLabel(voice_frame, text="Voice command", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=16, pady=(12, 0))
    ctk.CTkLabel(voice_frame, text="Say a keyword to launch workspace. Separate words with comma. Leave empty to disable.",
                 text_color="#888").pack(anchor="w", padx=16, pady=(2, 8))

    v1 = ctk.CTkFrame(voice_frame, fg_color="transparent")
    v1.pack(fill="x", padx=16, pady=(0, 6))
    ctk.CTkLabel(v1, text="Keywords:", text_color="#888").pack(side="left", padx=(0, 8))
    voice_kw_var = ctk.StringVar(value=cfg.get("slowa_kluczowe", ""))
    ctk.CTkEntry(v1, textvariable=voice_kw_var, height=32,
                  placeholder_text="e.g. launch, start workspace").pack(side="left", fill="x", expand=True)

    v2 = ctk.CTkFrame(voice_frame, fg_color="transparent")
    v2.pack(fill="x", padx=16, pady=(0, 12))
    ctk.CTkLabel(v2, text="Language:", text_color="#888").pack(side="left", padx=(0, 8))
    voice_lang_var = ctk.StringVar(value=cfg.get("jezyk_mowy", "en"))
    ctk.CTkOptionMenu(v2, variable=voice_lang_var, values=["pl", "en"], width=80, height=32).pack(side="left")
    ctk.CTkLabel(v2, text="Model ~50MB, downloaded once on first use.", text_color="#666").pack(side="left", padx=(12, 0))

    # Export / Import
    ei_frame = ctk.CTkFrame(set_scroll, corner_radius=10)
    ei_frame.pack(fill="x", padx=8, pady=(0, 8))
    ctk.CTkLabel(ei_frame, text="Export / Import configuration", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16, pady=(12, 4))
    ctk.CTkLabel(ei_frame, text="Share config with another user or load from file.", text_color="#888").pack(anchor="w", padx=16, pady=(0, 8))
    ei_btns = ctk.CTkFrame(ei_frame, fg_color="transparent")
    ei_btns.pack(fill="x", padx=16, pady=(0, 12))

    def do_export():
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")],
                                          initialfile="workspace-config-export.json")
        if not p: return
        # Build current config
        data = build_save_data()
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        messagebox.showinfo("Export", f"Configuration exported to:\n{p}")

    def do_import():
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not p: return
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Import", "Configuration imported!\nRestart WorkspaceConfig to see changes.")
            root.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import:\n{e}")

    ctk.CTkButton(ei_btns, text="Export", command=do_export, width=130, height=34,
                   fg_color="#444", hover_color="#555").pack(side="left", padx=(0, 8))
    ctk.CTkButton(ei_btns, text="Import", command=do_import, width=130, height=34,
                   fg_color="#444", hover_color="#555").pack(side="left")

    # ═══════════ Bottom bar buttons (added to pre-packed footer) ═══════════
    ctk.CTkButton(bottom, text="+ Add application", command=on_add, width=160, height=38,
                   fg_color="#444", hover_color="#555").pack(side="left", padx=(0, 8))

    def build_save_data():
        save_current_to_profile()
        return {
            "czulosc_klasniecia": czulosc.get(),
            "hotkey": hotkey_var.get(),
            "zdarzenie_dzwiekowe": trigger_var.get(),
            "liczba_zdarzen": int(count_var.get()),
            "cooldown": cooldown_var.get(),
            "czulosc_nn": round(nn_var.get(), 2),
            "slowa_kluczowe": voice_kw_var.get().strip(),
            "jezyk_mowy": voice_lang_var.get(),
            "profil_aktywny": prof_var.get(),
            "profile": current_profile["data"],
        }

    def save():
        data = build_save_data()

        # Validate active profile
        warnings = []
        active = data.get("profile", {}).get(data.get("profil_aktywny", ""), {})
        for a in active.get("aplikacje", []):
            exe = a.get("exe", "")
            if exe and not exe.startswith("shell:") and not os.path.exists(exe):
                warnings.append(f"App '{a['nazwa']}': {exe} does not exist")
        for t in active.get("terminale", []):
            folder = t.get("folder", "")
            if folder and not os.path.isdir(folder):
                warnings.append(f"Terminal '{t['nazwa']}': folder {folder} does not exist")

        if warnings:
            msg = "Issues found:\n\n" + "\n".join(f"• {w}" for w in warnings) + "\n\nSave anyway?"
            if not messagebox.askyesno("Validation", msg): return

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        sc = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "WorkspaceLauncher.lnk")
        if auto_var.get() and not os.path.exists(sc):
            lnch = os.path.join(BASE_DIR, "WorkspaceLauncher.exe")
            if os.path.exists(lnch):
                vp = os.path.join(BASE_DIR, "_t.vbs")
                with open(vp, "w") as fv:
                    fv.write(f'Set s=CreateObject("WScript.Shell").CreateShortcut("{sc}")\ns.TargetPath="{lnch}"\ns.WorkingDirectory="{BASE_DIR}"\ns.WindowStyle=7\ns.Save')
                subprocess.run(["cscript", "//nologo", vp], check=True)
                try: os.remove(vp)
                except: pass
        elif not auto_var.get() and os.path.exists(sc): os.remove(sc)

        messagebox.showinfo("Saved", "Configuration saved!")
        root.destroy()

    ctk.CTkButton(bottom, text="Cancel", command=root.destroy, width=100, height=38,
                   fg_color="#444", hover_color="#555").pack(side="right", padx=(8, 0))
    ctk.CTkButton(bottom, text="Save", command=save, width=120, height=38).pack(side="right")

    root.mainloop()

if __name__ == "__main__": main()
