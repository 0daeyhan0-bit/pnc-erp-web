' Hidden launcher for _git_snapshot.ps1 (no console window flash)
' Derives its own folder so no non-ASCII path literal is stored in this file.
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = scriptDir & "\_git_snapshot.ps1"
' 0 = hidden window, False = don't wait
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & ps1 & """", 0, False
