; ============================================================
; Workspace Launcher - keyboard shortcuts (AutoHotkey v2)
; ============================================================
; Instalacja: https://www.autohotkey.com/
; Run this file or add to startup
; ============================================================

; Ctrl+Alt+W -> profile "default"
^!w:: {
    Run('powershell.exe -ExecutionPolicy Bypass -File "' A_ScriptDir '\workspace-launcher.ps1" -Profile default')
}

; Ctrl+Alt+P -> profile "praca"
^!p:: {
    Run('powershell.exe -ExecutionPolicy Bypass -File "' A_ScriptDir '\workspace-launcher.ps1" -Profile praca')
}
