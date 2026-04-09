# ============================================================
# Workspace Launcher
# ============================================================
# Configuration in file: workspace-config.json
# ============================================================

param(
    [string]$Profile = "default",
    [switch]$ListMonitors
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $ScriptDir "workspace-config.json"

# --- Load configuration ---
if (-not (Test-Path $ConfigPath)) {
    Write-Host "ERROR: Configuration file not found: $ConfigPath" -ForegroundColor Red
    exit 1
}

$AllConfig = Get-Content $ConfigPath -Raw | ConvertFrom-Json
if (-not $AllConfig.profiles.PSObject.Properties[$Profile]) {
    Write-Host "ERROR: Unknown profile '$Profile'. Available: $($AllConfig.profiles.PSObject.Properties.Name -join ', ')" -ForegroundColor Red
    exit 1
}
$Config = $AllConfig.profiles.$Profile

# --- Win32 API for window management ---
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public class WinAPI {
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
}
"@

Add-Type -AssemblyName System.Windows.Forms

# --- Monitor list ---
if ($ListMonitors) {
    Write-Host "`nAvailable monitors:" -ForegroundColor Cyan
    $screens = [System.Windows.Forms.Screen]::AllScreens
    for ($i = 0; $i -lt $screens.Count; $i++) {
        $s = $screens[$i]
        $primary = if ($s.Primary) { " (PRIMARY)" } else { "" }
        Write-Host "  Monitor $i : $($s.Bounds.Width)x$($s.Bounds.Height) at ($($s.Bounds.X),$($s.Bounds.Y))$primary" -ForegroundColor White
    }
    Write-Host ""
    Write-Host "Use these numbers in workspace-config.json" -ForegroundColor Gray
    exit 0
}

# --- Helper functions ---
function Get-MonitorBounds([int]$Index) {
    $screens = [System.Windows.Forms.Screen]::AllScreens
    if ($Index -ge $screens.Count) {
        Write-Host "  ! Monitor $Index does not exist, using 0" -ForegroundColor Yellow
        $Index = 0
    }
    return $screens[$Index].WorkingArea
}

function Move-ToMonitor([IntPtr]$Handle, [int]$MonitorIndex) {
    if ($Handle -eq [IntPtr]::Zero) { return }
    $bounds = Get-MonitorBounds $MonitorIndex
    [WinAPI]::ShowWindow($Handle, 9) | Out-Null  # SW_RESTORE
    Start-Sleep -Milliseconds 300
    [WinAPI]::SetWindowPos($Handle, [IntPtr]::Zero, $bounds.X, $bounds.Y, $bounds.Width, $bounds.Height, 0x0044) | Out-Null
    Start-Sleep -Milliseconds 200
    [WinAPI]::ShowWindow($Handle, 3) | Out-Null  # SW_MAXIMIZE
}

function Find-ProcessWindow([string]$ProcessName, [int]$Timeout = 15) {
    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        $procs = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero }
        if ($procs) {
            return $procs[0].MainWindowHandle
        }
        Start-Sleep -Milliseconds 500
    }
    return [IntPtr]::Zero
}

function Find-WindowByTitle([string]$TitlePattern, [int]$Timeout = 15) {
    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        $result = [IntPtr]::Zero
        $callback = [WinAPI+EnumWindowsProc]{
            param($hWnd, $lParam)
            if ([WinAPI]::IsWindowVisible($hWnd) -and [WinAPI]::GetWindowTextLength($hWnd) -gt 0) {
                $sb = New-Object System.Text.StringBuilder 512
                [WinAPI]::GetWindowText($hWnd, $sb, 512) | Out-Null
                if ($sb.ToString() -match $TitlePattern) {
                    $script:matchedHwnd = $hWnd
                    return $false
                }
            }
            return $true
        }
        $script:matchedHwnd = [IntPtr]::Zero
        [WinAPI]::EnumWindows($callback, [IntPtr]::Zero) | Out-Null
        if ($script:matchedHwnd -ne [IntPtr]::Zero) {
            return $script:matchedHwnd
        }
        Start-Sleep -Milliseconds 500
    }
    return [IntPtr]::Zero
}

Write-Host ""
Write-Host "=== Workspace Launcher ===" -ForegroundColor Cyan
Write-Host "    Profile: $Profile" -ForegroundColor Gray
Write-Host ""

# ========================================
# 1. VS CODE
# ========================================
if ($Config.vscode.projects.Count -gt 0) {
    Write-Host "[1/4] VS Code..." -ForegroundColor Green
    foreach ($project in $Config.vscode.projects) {
        if (Test-Path $project) {
            Start-Process "code" -ArgumentList "`"$project`""
            Write-Host "  -> $project" -ForegroundColor Gray
        } else {
            Write-Host "  -> MISSING: $project" -ForegroundColor Yellow
        }
    }
    Start-Sleep -Seconds 4
    $hwnd = Find-WindowByTitle "Visual Studio Code" -Timeout 10
    if ($hwnd -ne [IntPtr]::Zero) {
        Move-ToMonitor $hwnd $Config.vscode.monitor
        Write-Host "  -> Monitor $($Config.vscode.monitor)" -ForegroundColor DarkGray
    } else {
        Write-Host "  ! VS Code window not found" -ForegroundColor Yellow
    }
}

# ========================================
# 2. MICROSOFT TEAMS
# ========================================
if ($Config.teams.enabled) {
    Write-Host "[2/4] Teams..." -ForegroundColor Green
    # New Teams (Windows 11)
    $teamsNew = "$env:LOCALAPPDATA\Microsoft\WindowsApps\ms-teams.exe"
    # Old Teams
    $teamsOld = "$env:LOCALAPPDATA\Microsoft\Teams\Update.exe"

    if (Test-Path $teamsNew) {
        Start-Process $teamsNew
    } elseif (Test-Path $teamsOld) {
        Start-Process $teamsOld -ArgumentList "--processStart", "Teams.exe"
    } else {
        Start-Process "msteams:"
    }
    Start-Sleep -Seconds 5
    $hwnd = Find-WindowByTitle "Teams" -Timeout 10
    if ($hwnd -ne [IntPtr]::Zero) {
        Move-ToMonitor $hwnd $Config.teams.monitor
        Write-Host "  -> Monitor $($Config.teams.monitor)" -ForegroundColor DarkGray
    }
}

# ========================================
# 3. SPOTIFY
# ========================================
if ($Config.spotify.enabled) {
    Write-Host "[3/4] Spotify..." -ForegroundColor Green

    # Launch Spotify
    $spotifyDesktop = "$env:APPDATA\Spotify\Spotify.exe"
    if (Test-Path $spotifyDesktop) {
        Start-Process $spotifyDesktop
    } else {
        Start-Process "spotify:"
    }
    Start-Sleep -Seconds 5

    # Search and play a song/playlist
    if ($Config.spotify.search) {
        $query = [Uri]::EscapeDataString($Config.spotify.search)
        Start-Process "spotify:search:$query"
        Write-Host "  -> Searching: '$($Config.spotify.search)'" -ForegroundColor Gray
        Write-Host "  -> Press Enter/Play in Spotify to play the result" -ForegroundColor DarkGray
    }

    Start-Sleep -Seconds 2
    $hwnd = Find-WindowByTitle "Spotify" -Timeout 10
    if ($hwnd -ne [IntPtr]::Zero) {
        Move-ToMonitor $hwnd $Config.spotify.monitor
        Write-Host "  -> Monitor $($Config.spotify.monitor)" -ForegroundColor DarkGray
    }
}

# ========================================
# 4. GIT BASH + CLAUDE CODE
# ========================================
if ($Config.claude.enabled) {
    Write-Host "[4/4] Git Bash + Claude..." -ForegroundColor Green
    $gitBash = "C:\Program Files\Git\git-bash.exe"
    $startDir = $Config.claude.path

    if (Test-Path $gitBash) {
        Start-Process $gitBash -ArgumentList "--cd=`"$startDir`""
        Write-Host "  -> $startDir" -ForegroundColor Gray
        Start-Sleep -Seconds 3
        $hwnd = Find-WindowByTitle "MINGW|MSYS|mintty" -Timeout 10
        if ($hwnd -ne [IntPtr]::Zero) {
            Move-ToMonitor $hwnd $Config.claude.monitor
            Write-Host "  -> Monitor $($Config.claude.monitor)" -ForegroundColor DarkGray
        }
    } else {
        Start-Process "wt.exe" -ArgumentList "new-tab", "-d", "`"$startDir`""
        Write-Host "  -> Windows Terminal" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=== Done! ===" -ForegroundColor Cyan
Write-Host ""
