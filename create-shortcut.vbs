Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
distDir = fso.BuildPath(scriptDir, "dist")
exePath = fso.BuildPath(distDir, "WorkspaceLauncher.exe")

Set s=CreateObject("WScript.Shell").CreateShortcut(CreateObject("WScript.Shell").ExpandEnvironmentStrings("%APPDATA%") & "\Microsoft\Windows\Start Menu\Programs\Startup\WorkspaceLauncher.lnk")
s.TargetPath=exePath
s.WorkingDirectory=distDir
s.Description="Workspace Launcher - double clap"
s.WindowStyle=7
s.Save
WScript.Echo "Startup shortcut created!"
