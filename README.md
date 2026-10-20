# Codex & Antigravity Usage Widget

Small, elegant, always-on-top Windows desktop widget for tracking your latest **Codex** and **Antigravity** usage and rate limits locally.

> Unofficial utility. This is not an OpenAI or Google plugin and not an official feature of either product.

```text
+---------------------------------------------+
| [ Codex | Anti ]                     ↻   ×  |
| ● 快照 13:35 (最新)                         |
| 5 小时                               无限制 |
| 1 周         [ 10-25 07:40 ]       剩余 11% |
+---------------------------------------------+
```

## What This Is

If you often open account menus just to check remaining usage and reset times, this tool keeps a tiny floating widget on your desktop.

It provides a dual-view tabbed interface allowing you to freely switch between:
- **Codex**: Parses the latest rate-limit snapshot from local Codex session logs (`%USERPROFILE%\.codex\sessions\**\*.jsonl`).
- **Antigravity**: Connects to the local Antigravity Language Server RPC to display live quotas for `Gemini Models`, `Claude / GPT`, and `Gemini 4 Argon`.

### Key Highlights

- **Compact & Distraction-Free**: Tiny footprint (`232x134`), borderless, semi-transparent (`0.98`), always-on-top.
- **Full-Card Draggable**: Grab and drag the widget from anywhere on the card.
- **Zero Third-Party Dependencies**: Written entirely with Python standard libraries (`tkinter`, `urllib`, `ssl`, `ctypes`, etc.) — no `pip install` required.
- **Gentle 5-Minute Auto-Refresh**: Background timer quietly refreshes data every 5 minutes, or instantly on-demand via the `↻` button.
- **Private & 100% Local**: No external cloud calls; only reads local files and local loopback RPC.

## Features

- **Dual-Mode Tabs**: Seamlessly switch between `[ Codex ]` and `[ Anti ]` views in the header.
- **Antigravity Model Pills**: In Anti mode, switch between `Gemini`, `Claude`, and `Argon` categories with a single click.
- **Smart Window Routing**: Automatically maps short-term (5-hour) and long-term (weekly) quotas according to `window_minutes`, gracefully handling tiers like Prolite that only enforce weekly quotas without awkward placeholders.
- **Precise Reset Times**: Displays `HH:MM` for same-day resets, or `MM-DD HH:MM` for upcoming dates.
- **Color-Coded Status**: Percentages change dynamically (Green $\ge 20\%$, Amber $< 20\%$, Red $< 5\%$).
- **Snapshot Age Indicator**: Clear timestamp status indicator (e.g. `● 快照 13:35 (最新)` or `● 快照 13:35 (25m 前)`).
- **Windows Login Autostart**: Easily enable/disable startup on Windows login without administrator privileges or registry changes.

## Files

- [codex_usage_widget.py](./codex_usage_widget.py): Core Python widget application
- [launch_codex_usage_widget.vbs](./launch_codex_usage_widget.vbs): Windows silent launcher (starts Python with no console black window)
- [enable_startup.vbs](./enable_startup.vbs): Double-click helper to enable Windows login autostart
- [disable_startup.vbs](./disable_startup.vbs): Double-click helper to disable Windows login autostart

## Requirements

- Windows 10 / 11
- Python 3 with `tkinter` (included in standard Python Windows installer)
- Codex desktop (for Codex quota view)
- Antigravity IDE (for Anti quota view)

## Quick Start

### Option 1: Double-click (Recommended)
Run [launch_codex_usage_widget.vbs](./launch_codex_usage_widget.vbs).

### Option 2: PowerShell
```powershell
python .\codex_usage_widget.py
```

To start directly in Antigravity mode:
```powershell
python .\codex_usage_widget.py --mode anti
```

## Startup At Login

You can enable automatic startup when signing in to Windows:

### Double-click
- Enable: [enable_startup.vbs](./enable_startup.vbs)
- Disable: [disable_startup.vbs](./disable_startup.vbs)

### PowerShell
```powershell
python .\codex_usage_widget.py --install-startup
python .\codex_usage_widget.py --startup-status
python .\codex_usage_widget.py --remove-startup
```

## CLI Arguments

```powershell
python .\codex_usage_widget.py --mode anti
python .\codex_usage_widget.py --corner top-left
python .\codex_usage_widget.py --codex-home "D:\Custom\.codex"
python .\codex_usage_widget.py --once
```

Available options:
- `--mode`: Initial mode, either `codex` or `anti` (default: `codex`)
- `--interval`: Auto-refresh interval in minutes (default: `5`, set `0` to disable)
- `--corner`: Initial screen placement: `top-right`, `top-left`, `bottom-right`, `bottom-left`
- `--codex-home`: Custom Codex data directory (defaults to `%USERPROFILE%\.codex`)
- `--once`: Output the latest parsed snapshot for both Codex and Antigravity to terminal and exit
- `--install-startup`: Install autostart script in user's Startup folder
- `--remove-startup`: Remove autostart script
- `--startup-status`: Check current startup status
