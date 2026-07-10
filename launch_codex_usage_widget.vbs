Option Explicit

Dim fso
Dim shell
Dim runtimePython
Dim scriptPath
Dim command
Dim argText
Dim i
Dim shouldWait
Dim exitCode

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

runtimePython = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
scriptPath = fso.GetParentFolderName(WScript.ScriptFullName) & "\codex_usage_widget.py"
argText = ""

If Not fso.FileExists(scriptPath) Then
  MsgBox "Could not find codex_usage_widget.py", vbCritical, "Codex Usage Widget"
  WScript.Quit 1
End If

If fso.FileExists(runtimePython) Then
  command = """" & runtimePython & """ """ & scriptPath & """"
Else
  command = "python """ & scriptPath & """"
End If

If WScript.Arguments.Count > 0 Then
  shouldWait = True
  For i = 0 To WScript.Arguments.Count - 1
    argText = argText & " """ & WScript.Arguments(i) & """"
  Next
Else
  shouldWait = False
End If

exitCode = shell.Run(command & argText, 0, shouldWait)
If shouldWait Then
  WScript.Quit exitCode
End If
