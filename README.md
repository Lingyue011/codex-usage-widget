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
- Uses only Python standard library modules such as `tkinter`

## How It Works

The widget reads the latest `token_count` event and its `rate_limits` data from local Codex session logs, typically under:

- `%USERPROFILE%\.codex\sessions\**\*.jsonl`

If you use a custom Codex home directory, you can override it with `--codex-home`.

This tool does **not** call any remote API. It only reads files that Codex already stores locally on your machine.

## Files

- [codex_usage_widget.py](./codex_usage_widget.py): main widget
- [launch_codex_usage_widget.vbs](./launch_codex_usage_widget.vbs): Windows double-click launcher

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
