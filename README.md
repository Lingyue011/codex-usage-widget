# Codex Usage Widget

A tiny Windows floating window that shows your latest Codex usage snapshot from local session logs.

## What it shows

- `5 小时` window remaining percent and reset time
- `1 周` window remaining percent and reset time
- a small status badge for `手动`, `等待`, or `滞后`

## Why this is a standalone widget

Codex plugins are built to bundle skills, app integrations, and MCP servers. They are not a general desktop UI extension point for arbitrary always-on-top windows.

Codex does have a built-in floating overlay for active thread status, but it does not show the quota panel values.

## Run it

Double-click:

- [launch_codex_usage_widget.vbs](/C:/Users/13949/OneDrive/PythonCode/codex_usage_widget/launch_codex_usage_widget.vbs)

Or run from PowerShell:

```powershell
C:\Users\13949\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe `
  C:\Users\13949\OneDrive\PythonCode\codex_usage_widget\codex_usage_widget.py
```

## Debug mode

Print the latest parsed snapshot once:

```powershell
C:\Users\13949\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe `
  C:\Users\13949\OneDrive\PythonCode\codex_usage_widget\codex_usage_widget.py --once
```

## Notes

- The widget reads `C:\Users\13949\.codex\sessions\**\*.jsonl`.
- It reads once on startup.
- After that, it only rescans when you click the refresh button.
- If Codex has not written a new `token_count` event yet, the widget can only show the last logged snapshot.
- The window starts in the top-right corner, stays on top, and can be dragged anywhere.
