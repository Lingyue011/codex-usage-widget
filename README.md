# Codex Usage Widget

Small always-on-top Windows widget for viewing the latest Codex usage snapshot from local logs.

> Unofficial utility. This is not an OpenAI plugin and not an official Codex feature.

## What This Is

If you often open the Codex account menu just to check `Remaining usage`, this tool keeps a tiny floating panel on your desktop and shows the latest usage snapshot that Codex has already written to local session logs.

It is designed to be:

- small
- manual-refresh only
- easy to share
- dependency-light

## Features

- Shows both usage windows: `5 hours` and `1 week`
- Shows the next reset time for each window
- Always on top and draggable
- Reads once on startup, then refreshes only when you click the refresh button
- Supports Windows login startup via the user Startup folder
- Uses only Python standard library modules such as `tkinter`

## How It Works

The widget reads the latest `token_count` event and its `rate_limits` data from local Codex session logs, typically under:

- `%USERPROFILE%\.codex\sessions\**\*.jsonl`

If you use a custom Codex home directory, you can override it with `--codex-home`.

This tool does **not** call any remote API. It only reads files that Codex already stores locally on your machine.

## Files

- [codex_usage_widget.py](./codex_usage_widget.py): main widget
- [launch_codex_usage_widget.vbs](./launch_codex_usage_widget.vbs): Windows double-click launcher
- [enable_startup.vbs](./enable_startup.vbs): double-click helper to enable login startup
- [disable_startup.vbs](./disable_startup.vbs): double-click helper to disable login startup

## Requirements

- Windows
- Codex desktop with local session logs
- Python 3
- `tkinter` available in your Python installation

## Quick Start

### Option 1: Double-click

Run:

- [launch_codex_usage_widget.vbs](./launch_codex_usage_widget.vbs)

### Option 2: PowerShell

```powershell
python .\codex_usage_widget.py
```

## Startup At Login

This update adds optional Windows login startup. When enabled, the widget launches automatically after the current Windows user signs in.

It works by creating a small per-user startup stub:

- `Codex Usage Widget Startup.vbs`

inside the Windows Startup folder:

- `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`

The startup helper calls [launch_codex_usage_widget.vbs](./launch_codex_usage_widget.vbs), which then starts [codex_usage_widget.py](./codex_usage_widget.py). It does not require administrator access and does not write to the Windows registry.

### Easiest way

Double-click:

- [enable_startup.vbs](./enable_startup.vbs)

This installs the startup stub for the current Windows user. The widget will start the next time you sign in to Windows.

To turn auto-start off later, double-click:

- [disable_startup.vbs](./disable_startup.vbs)

This removes only the startup stub. It does not delete the widget files.

### PowerShell

```powershell
python .\codex_usage_widget.py --install-startup
python .\codex_usage_widget.py --startup-status
python .\codex_usage_widget.py --remove-startup
```

Use:

- `--install-startup` to enable auto-start
- `--startup-status` to print the current startup configuration
- `--remove-startup` to disable auto-start

Only one of these startup commands should be used at a time.

## Optional Arguments

```powershell
python .\codex_usage_widget.py --corner top-left
python .\codex_usage_widget.py --codex-home "D:\Custom\.codex"
python .\codex_usage_widget.py --once
```

Available options:

- `--corner`: initial position, one of `top-right`, `top-left`, `bottom-right`, `bottom-left`
- `--codex-home`: custom Codex data directory
- `--once`: print the latest parsed snapshot once and exit
- `--install-startup`: enable login startup for the current Windows user
- `--remove-startup`: disable login startup for the current Windows user
- `--startup-status`: print the current startup configuration

## Share With Others

The project is self-contained and easy to pass around.

You can share it by:

- sending the GitHub repository link
- letting someone download the repository ZIP
- copying the project folder directly

For normal use, the important files are:

- `codex_usage_widget.py`
- `launch_codex_usage_widget.vbs`

## Limitations

- The widget can only show the latest snapshot that Codex has already written to local logs.
- If Codex has not written a newer `token_count` event yet, clicking refresh will still show the previous saved values.
- This project is currently intended for Windows desktop use.

## Privacy

This tool only reads local Codex session files on your machine. It does not upload usage data anywhere by itself.

## Notes

- The window is intentionally minimal and compact.
- Manual refresh is used by design to avoid continuous background scanning.
- This repository is meant to share a lightweight local utility, not a full Codex extension system.
