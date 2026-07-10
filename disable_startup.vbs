Option Explicit

Dim fso
Dim shell
Dim launcherPath
Dim command
Dim exitCode

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

launcherPath = fso.GetParentFolderName(WScript.ScriptFullName) & "\launch_codex_usage_widget.vbs"

If Not fso.FileExists(launcherPath) Then
  MsgBox "Could not find launch_codex_usage_widget.vbs", vbCritical, "Codex Usage Widget"
  WScript.Quit 1
End If

command = "wscript.exe " & Chr(34) & launcherPath & Chr(34) & " --remove-startup"
exitCode = shell.Run(command, 0, True)

If exitCode = 0 Then
  MsgBox "Startup disabled.", vbInformation, "Codex Usage Widget"
Else
  MsgBox "Could not disable startup.", vbCritical, "Codex Usage Widget"
End If
