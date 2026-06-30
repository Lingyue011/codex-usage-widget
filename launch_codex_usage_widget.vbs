Option Explicit

Dim fso
Dim shell
Dim runtimePython
Dim scriptPath
Dim command

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

runtimePython = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
scriptPath = fso.GetParentFolderName(WScript.ScriptFullName) & "\codex_usage_widget.py"

If Not fso.FileExists(scriptPath) Then
  MsgBox "Could not find codex_usage_widget.py", vbCritical, "Codex Usage Widget"
  WScript.Quit 1
End If

If fso.FileExists(runtimePython) Then
  command = """" & runtimePython & """ """ & scriptPath & """"
Else
  command = "python """ & scriptPath & """"
End If

shell.Run command, 0, False
