$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WshShell = New-Object -ComObject WScript.Shell
$ShortcutPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\ClapTrigger.lnk"
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "$env:LOCALAPPDATA\Programs\Python\Python314\pythonw.exe"
$Shortcut.Arguments = "`"$ScriptDir\clap-trigger.py`" --profile default"
$Shortcut.WorkingDirectory = $ScriptDir
$Shortcut.Description = "Clap Trigger - Workspace Launcher"
$Shortcut.WindowStyle = 7  # Minimized
$Shortcut.Save()
Write-Host "Shortcut created: $ShortcutPath" -ForegroundColor Green
