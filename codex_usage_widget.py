from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import ssl
import subprocess
import sys
import time
import tkinter as tk
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

MAX_CANDIDATE_FILES = 24
MAX_TAIL_BYTES = 256 * 1024
WINDOW_WIDTH = 232
WINDOW_HEIGHT = 134
WINDOW_MARGIN = 12
AUTO_REFRESH_INTERVAL_MS = 5 * 60 * 1000  # 5 minutes
STARTUP_STUB_NAME = "Codex Usage Widget Startup.vbs"

# Refined Modern Warm Palette
CARD_BG = "#F6F1EC"
CARD_BORDER = "#DDD3C6"
ROW_BG = "#FFFFFF"
ROW_BORDER = "#E9E0D5"
TEXT_PRIMARY = "#2A241E"
TEXT_SECONDARY = "#766A5C"
TEXT_MUTED = "#A29587"
TEXT_ACCENT = "#0E7A53"
TEXT_WARN = "#B86715"
TEXT_DANGER = "#C72420"
BADGE_BG = "#EFE8DD"
BUTTON_BG = "#EAE1D3"
BUTTON_ACTIVE = "#DFD5C6"
TAB_ACTIVE_BG = "#2A241E"
TAB_ACTIVE_FG = "#FFFFFF"
TAB_INACTIVE_BG = "#E6DECF"
TAB_INACTIVE_FG = "#6A5E50"

LABEL_FIVE_HOURS = "5 小时"
LABEL_ONE_WEEK = "1 周"
TEXT_WAITING = "等待"
TEXT_UNLIMITED = "无限制"


def is_pid_running(pid: int) -> bool:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    try:
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
    except Exception:
        pass
    return False


def format_reset_time(val: int | float | datetime | str | None) -> str:
    if not val:
        return "--"
    try:
        if isinstance(val, (int, float)):
            dt = datetime.fromtimestamp(val, tz=timezone.utc).astimezone()
        elif isinstance(val, str):
            dt = datetime.fromisoformat(val.replace("Z", "+00:00")).astimezone()
        elif isinstance(val, datetime):
            dt = val.astimezone()
        else:
            return "--"
    except Exception:
        return "--"

    now = datetime.now().astimezone()
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    if dt.year == now.year:
        return dt.strftime("%m-%d %H:%M")
    return dt.strftime("%y-%m-%d %H:%M")


def format_snapshot_age(ts: datetime | None) -> tuple[str, str]:
    if ts is None:
        return "● 未找到日志快照", TEXT_WARN

    local_dt = ts.astimezone()
    time_str = local_dt.strftime("%H:%M")
    age_seconds = (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds()

    if age_seconds <= 20 * 60:
        return f"● 快照 {time_str} (最新)", TEXT_ACCENT
    elif age_seconds < 3600:
        mins = int(age_seconds // 60)
        return f"● 快照 {time_str} ({mins}m 前)", TEXT_WARN
    else:
        hours = int(age_seconds // 3600)
        return f"● 快照 {time_str} ({hours}h 前)", TEXT_WARN


def clamp_percent(value: float | int | None) -> int | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    numeric = max(0.0, min(100.0, numeric))
    return int(round(numeric))


def get_percent_color(remaining: int | None) -> str:
    if remaining is None:
        return TEXT_MUTED
    if remaining >= 20:
        return TEXT_ACCENT
    if remaining >= 5:
        return TEXT_WARN
    return TEXT_DANGER


def appdata_dir() -> Path:
    raw = os.environ.get("APPDATA")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / "AppData" / "Roaming"


def startup_folder() -> Path:
    return appdata_dir() / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def launcher_path() -> Path:
    return Path(__file__).resolve().with_name("launch_codex_usage_widget.vbs")


def startup_stub_path() -> Path:
    return startup_folder() / STARTUP_STUB_NAME


def startup_stub_contents() -> str:
    launcher_literal = str(launcher_path())
    return (
        "Option Explicit\r\n\r\n"
        "Dim shell\r\n"
        "Set shell = CreateObject(\"WScript.Shell\")\r\n"
        f"shell.Run Chr(34) & \"{launcher_literal}\" & Chr(34), 0, False\r\n"
    )


def startup_enabled() -> bool:
    return startup_stub_path().exists()


def install_startup() -> str:
    launcher = launcher_path()
    if not launcher.exists():
        raise FileNotFoundError(f"Launcher not found: {launcher}")

    folder = startup_folder()
    folder.mkdir(parents=True, exist_ok=True)
    stub = startup_stub_path()
    stub.write_text(startup_stub_contents(), encoding="ascii", newline="")
    return str(stub)


def remove_startup() -> str:
    stub = startup_stub_path()
    if stub.exists():
        stub.unlink()
    return str(stub)


def startup_status_payload() -> dict[str, str | bool]:
    return {
        "enabled": startup_enabled(),
        "startup_folder": str(startup_folder()),
        "startup_stub": str(startup_stub_path()),
        "launcher": str(launcher_path()),
    }


def default_codex_home() -> Path:
    raw = os.environ.get("CODEX_HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".codex"


def parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def iter_tail_lines(path: Path, max_bytes: int = MAX_TAIL_BYTES) -> Iterable[str]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        handle.seek(max(0, size - max_bytes))
        block = handle.read()
    for raw_line in reversed(block.splitlines()):
        yield raw_line.decode("utf-8", errors="replace").strip()


# -------------------------------------------------------------
# Codex Models & Finder
# -------------------------------------------------------------

@dataclass
class LimitWindow:
    used_percent: int | None
    window_minutes: int | None
    resets_at: int | None

    @property
    def remaining_percent(self) -> int | None:
        if self.used_percent is None:
            return None
        return max(0, 100 - self.used_percent)

    @property
    def reset_text(self) -> str:
        return format_reset_time(self.resets_at)


@dataclass
class CodexSnapshot:
    source_file: Path
    timestamp: datetime | None
    five_hour: LimitWindow | None
    weekly: LimitWindow | None

    @property
    def is_stale(self) -> bool:
        if self.timestamp is None:
            return True
        age = datetime.now(timezone.utc) - self.timestamp.astimezone(timezone.utc)
        return age.total_seconds() > 20 * 60


def parse_codex_limit_window(payload: dict) -> LimitWindow:
    return LimitWindow(
        used_percent=clamp_percent(payload.get("used_percent")),
        window_minutes=payload.get("window_minutes"),
        resets_at=payload.get("resets_at"),
    )


def extract_codex_snapshot(path: Path) -> CodexSnapshot | None:
    try:
        for line in iter_tail_lines(path):
            if '"token_count"' not in line or '"rate_limits"' not in line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("type") != "event_msg":
                continue
            payload = item.get("payload") or {}
            if payload.get("type") != "token_count":
                continue
            rate_limits = payload.get("rate_limits") or {}

            # Intelligently route by window_minutes to prevent mismatch
            five_h = None
            weekly = None
            for key in ("primary", "secondary"):
                raw_w = rate_limits.get(key)
                if not raw_w or not isinstance(raw_w, dict):
                    continue
                w = parse_codex_limit_window(raw_w)
                wm = w.window_minutes
                if wm is not None:
                    if wm <= 720:  # <= 12 hours (e.g. 300 = 5 hours)
                        five_h = w
                    else:  # e.g. 10080 = 7 days = 1 week
                        weekly = w
                else:
                    if key == "primary":
                        five_h = w
                    else:
                        weekly = w

            return CodexSnapshot(
                source_file=path,
                timestamp=parse_timestamp(item.get("timestamp")),
                five_hour=five_h,
                weekly=weekly,
            )
    except OSError:
        return None
    return None


class CodexSnapshotFinder:
    def __init__(self, codex_home: Path) -> None:
        self.codex_home = codex_home
        self.sessions_root = codex_home / "sessions"
        self.current_file: Path | None = None
        self.cached_candidates: list[Path] = []
        self.last_scan_at = 0.0

    def candidate_files(self, force_rescan: bool = False) -> list[Path]:
        now = time.monotonic()
        if self.cached_candidates and not force_rescan and now - self.last_scan_at < 300:
            return self.cached_candidates

        candidates: list[tuple[float, Path]] = []
        for path in self.sessions_root.rglob("*.jsonl"):
            try:
                candidates.append((path.stat().st_mtime, path))
            except OSError:
                continue

        candidates.sort(key=lambda item: item[0], reverse=True)
        self.cached_candidates = [path for _mtime, path in candidates[:MAX_CANDIDATE_FILES]]
        self.last_scan_at = now
        return self.cached_candidates

    def find_latest(self, force_rescan: bool = False) -> CodexSnapshot | None:
        candidates: list[Path] = []
        if self.current_file is not None and self.current_file.exists():
            candidates.append(self.current_file)
        for path in self.candidate_files(force_rescan=force_rescan):
            if path not in candidates:
                candidates.append(path)

        freshest: CodexSnapshot | None = None
        for path in candidates:
            snapshot = extract_codex_snapshot(path)
            if snapshot is None:
                continue
            if freshest is None:
                freshest = snapshot
                continue
            current_ts = freshest.timestamp or datetime.fromtimestamp(0, tz=timezone.utc)
            snapshot_ts = snapshot.timestamp or datetime.fromtimestamp(0, tz=timezone.utc)
            if snapshot_ts > current_ts:
                freshest = snapshot

        if freshest is not None:
            self.current_file = freshest.source_file
        return freshest


# -------------------------------------------------------------
# Antigravity Models & Finder
# -------------------------------------------------------------

@dataclass
class AntiBucket:
    bucket_id: str
    display_name: str
    window: str
    remaining_percent: int | None
    reset_text: str


@dataclass
class AntiGroup:
    key: str
    display_name: str
    five_hour: AntiBucket | None
    weekly: AntiBucket | None


@dataclass
class AntiSnapshot:
    timestamp: datetime
    groups: dict[str, AntiGroup]


def parse_anti_snapshot(payload: dict) -> AntiSnapshot:
    groups_data = payload.get("response", {}).get("groups", [])
    groups: dict[str, AntiGroup] = {}

    for g in groups_data:
        disp = g.get("displayName", "")
        buckets = g.get("buckets", [])

        five_h = None
        weekly = None
        for b in buckets:
            win = b.get("window", "")
            rem_frac = b.get("remainingFraction")
            rem_pct = clamp_percent(rem_frac * 100 if rem_frac is not None else None)
            res_txt = format_reset_time(b.get("resetTime"))
            bucket = AntiBucket(
                bucket_id=b.get("bucketId", ""),
                display_name=b.get("displayName", ""),
                window=win,
                remaining_percent=rem_pct,
                reset_text=res_txt,
            )
            if win == "5h" or "5 Hour" in b.get("displayName", ""):
                five_h = bucket
            elif win == "weekly" or "Weekly" in b.get("displayName", ""):
                weekly = bucket
            else:
                if five_h is None:
                    five_h = bucket
                elif weekly is None:
                    weekly = bucket

        if "Argon" in disp:
            key = "argon"
            short_name = "Argon"
        elif "Claude" in disp or "GPT" in disp:
            key = "claude"
            short_name = "Claude"
        elif "Gemini" in disp:
            key = "gemini"
            short_name = "Gemini"
        else:
            key = disp.lower().replace(" ", "_")
            short_name = disp

        groups[key] = AntiGroup(
            key=key,
            display_name=short_name,
            five_hour=five_h,
            weekly=weekly,
        )

    return AntiSnapshot(timestamp=datetime.now(timezone.utc), groups=groups)


class AntigravityQuotaFinder:
    def __init__(self) -> None:
        self.cached_pid: int | None = None
        self.cached_csrf: str | None = None
        self.cached_ports: list[int] = []

    def _discover(self) -> bool:
        if self.cached_pid and self.cached_csrf and self.cached_ports:
            if is_pid_running(self.cached_pid):
                return True

        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name = 'language_server.exe'\" | "
            "ForEach-Object { $p = $_; $ports = (Get-NetTCPConnection -OwningProcess $p.ProcessId -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty LocalPort); "
            "[PSCustomObject]@{ pid = $p.ProcessId; cmdline = $p.CommandLine; ports = $ports } } | ConvertTo-Json"
        ]
        try:
            out = subprocess.check_output(cmd, text=True, timeout=5)
            data = json.loads(out)
            if isinstance(data, list):
                data = data[0]
            cmdline = data.get("cmdline", "")
            m = re.search(r"--csrf_token\s+([a-zA-Z0-9_-]+)", cmdline)
            csrf = m.group(1) if m else None
            ports = data.get("ports", [])
            if isinstance(ports, int):
                ports = [ports]
            self.cached_pid = data.get("pid")
            self.cached_csrf = csrf
            self.cached_ports = ports
            return bool(csrf and ports)
        except Exception:
            return False

    def fetch_snapshot(self) -> AntiSnapshot | None:
        if not self._discover():
            return None

        ctx = ssl._create_unverified_context()
        for port in self.cached_ports:
            url = f"https://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary"
            headers = {
                "Content-Type": "application/json",
                "Connect-Protocol-Version": "1",
                "X-Codeium-Csrf-Token": self.cached_csrf or "",
            }
            req = urllib.request.Request(url, data=b"{}", headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, context=ctx, timeout=2) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                    return parse_anti_snapshot(payload)
            except Exception:
                continue

        # Invalidate cache if all ports failed
        self.cached_pid = None
        return None


# -------------------------------------------------------------
# GUI Widget
# -------------------------------------------------------------

class UsageWidget:
    def __init__(self, root: tk.Tk, codex_home: Path, corner: str, initial_mode: str = "codex") -> None:
        self.root = root
        self.corner = corner
        self.mode = initial_mode  # "codex" or "anti"
        self.active_anti_key = "argon"

        self.codex_finder = CodexSnapshotFinder(codex_home)
        self.anti_finder = AntigravityQuotaFinder()

        self.last_codex_snapshot: CodexSnapshot | None = None
        self.last_anti_snapshot: AntiSnapshot | None = None

        self.drag_offset_x = 0
        self.drag_offset_y = 0

        self.root.title("Codex & Anti Usage Widget")
        self.root.configure(bg=CARD_BG)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.98)

        # Outer card frame
        self.outer = tk.Frame(
            self.root,
            bg=CARD_BG,
            highlightbackground=CARD_BORDER,
            highlightthickness=1,
            bd=0,
        )
        self.outer.pack(fill="both", expand=True)

        # Header bar
        self.header = tk.Frame(self.outer, bg=CARD_BG)
        self.header.pack(fill="x", padx=9, pady=(6, 2))

        # Segmented Control Tab Frame
        self.tab_container = tk.Frame(
            self.header,
            bg=TAB_INACTIVE_BG,
            highlightbackground=CARD_BORDER,
            highlightthickness=1,
            bd=0,
        )
        self.tab_container.pack(side="left")

        self.tab_codex = self.make_tab_button(self.tab_container, "Codex", lambda: self.set_mode("codex"))
        self.tab_codex.pack(side="left")

        self.tab_anti = self.make_tab_button(self.tab_container, "Anti", lambda: self.set_mode("anti"))
        self.tab_anti.pack(side="left")

        # Top Control Buttons (Close packed first -> stays at the far right!)
        self.close_button = self.make_icon_button(self.header, "\u00d7", lambda _e: self.root.destroy())
        self.close_button.pack(side="right")

        self.refresh_button = self.make_icon_button(self.header, "\u21bb", lambda _e: self.refresh(force_rescan=True))
        self.refresh_button.pack(side="right", padx=(0, 4))

        # Sub-bar (Codex status line / Anti model pills)
        self.sub_bar_codex = tk.Frame(self.outer, bg=CARD_BG)
        self.status_label = tk.Label(
            self.sub_bar_codex,
            text="● 本地日志快照",
            bg=CARD_BG,
            fg=TEXT_SECONDARY,
            font=("Segoe UI", 8),
            anchor="w",
        )
        self.status_label.pack(side="left", padx=(1, 0))

        self.sub_bar_anti = tk.Frame(self.outer, bg=CARD_BG)
        self.anti_pills: dict[str, tk.Label] = {}
        for key, name in [("gemini", "Gemini"), ("claude", "Claude"), ("argon", "Argon")]:
            btn = self.make_pill_button(self.sub_bar_anti, name, (lambda k=key: self.set_anti_group(k)))
            btn.pack(side="left", padx=(0, 4))
            self.anti_pills[key] = btn

        # Rows (Compact 5h and Weekly cards)
        self.row_five_h = self.make_row(LABEL_FIVE_HOURS)
        self.row_weekly = self.make_row(LABEL_ONE_WEEK)

        # Full-card drag support
        self.bind_drag(self.root)

        self.root.update_idletasks()
        self.place_in_corner()
        self.set_mode(self.mode)

        # Start gentle background auto-refresh timer (every 5 mins)
        self.schedule_auto_refresh()

    def schedule_auto_refresh(self) -> None:
        self.root.after(AUTO_REFRESH_INTERVAL_MS, self._on_auto_refresh)

    def _on_auto_refresh(self) -> None:
        try:
            self.refresh(force_rescan=False)
        finally:
            self.schedule_auto_refresh()

    def make_icon_button(self, parent: tk.Widget, text: str, on_click) -> tk.Label:
        btn = tk.Label(
            parent,
            text=text,
            bg=BUTTON_BG,
            fg=TEXT_PRIMARY,
            font=("Segoe UI Symbol", 8, "bold"),
            width=2,
            cursor="hand2",
            padx=1,
            pady=0,
        )
        btn._is_interactive = True
        btn.bind("<Button-1>", on_click)
        btn.bind("<Enter>", lambda _e: btn.config(bg=BUTTON_ACTIVE))
        btn.bind("<Leave>", lambda _e: btn.config(bg=BUTTON_BG))
        return btn

    def make_tab_button(self, parent: tk.Widget, text: str, on_click) -> tk.Label:
        tab = tk.Label(
            parent,
            text=text,
            bg=TAB_INACTIVE_BG,
            fg=TAB_INACTIVE_FG,
            font=("Segoe UI", 8, "bold"),
            padx=7,
            pady=1,
            cursor="hand2",
        )
        tab._is_interactive = True
        tab.bind("<Button-1>", lambda _e: on_click())
        return tab

    def make_pill_button(self, parent: tk.Widget, text: str, on_click) -> tk.Label:
        pill = tk.Label(
            parent,
            text=text,
            bg=BUTTON_BG,
            fg=TAB_INACTIVE_FG,
            font=("Segoe UI", 7, "bold"),
            padx=6,
            pady=1,
            cursor="hand2",
        )
        pill._is_interactive = True
        pill.bind("<Button-1>", lambda _e: on_click())
        return pill

    def make_row(self, label_text: str) -> dict[str, tk.Label | tk.Frame]:
        card = tk.Frame(
            self.outer,
            bg=ROW_BG,
            highlightbackground=ROW_BORDER,
            highlightthickness=1,
            bd=0,
        )
        card.pack(fill="x", padx=9, pady=(0, 4))

        row = tk.Frame(card, bg=ROW_BG)
        row.pack(fill="x", padx=8, pady=4)

        label = tk.Label(
            row,
            text=label_text,
            bg=ROW_BG,
            fg=TEXT_PRIMARY,
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        )
        label.pack(side="left")

        remaining = tk.Label(
            row,
            text="--",
            bg=ROW_BG,
            fg=TEXT_ACCENT,
            anchor="e",
            font=("Segoe UI", 9, "bold"),
        )
        remaining.pack(side="right")

        reset = tk.Label(
            row,
            text="",
            bg=BADGE_BG,
            fg=TEXT_SECONDARY,
            anchor="e",
            font=("Segoe UI", 7, "bold"),
            padx=5,
            pady=1,
        )
        # badge is packed right before remaining when text is present

        return {"card": card, "row": row, "label": label, "remaining": remaining, "reset": reset}

    def bind_drag(self, widget: tk.Widget) -> None:
        if not getattr(widget, "_is_interactive", False):
            widget.bind("<ButtonPress-1>", self.start_drag)
            widget.bind("<B1-Motion>", self.on_drag)
        for child in widget.winfo_children():
            self.bind_drag(child)

    def start_drag(self, event: tk.Event) -> None:
        self.drag_offset_x = event.x_root - self.root.winfo_x()
        self.drag_offset_y = event.y_root - self.root.winfo_y()

    def on_drag(self, event: tk.Event) -> None:
        x = event.x_root - self.drag_offset_x
        y = event.y_root - self.drag_offset_y
        self.root.geometry(f"+{x}+{y}")

    def place_in_corner(self) -> None:
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        if self.corner == "top-left":
            x = WINDOW_MARGIN
            y = WINDOW_MARGIN
        elif self.corner == "bottom-left":
            x = WINDOW_MARGIN
            y = screen_height - WINDOW_HEIGHT - WINDOW_MARGIN
        elif self.corner == "bottom-right":
            x = screen_width - WINDOW_WIDTH - WINDOW_MARGIN
            y = screen_height - WINDOW_HEIGHT - WINDOW_MARGIN
        else:
            x = screen_width - WINDOW_WIDTH - WINDOW_MARGIN
            y = WINDOW_MARGIN

        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        if mode == "codex":
            self.tab_codex.config(bg=TAB_ACTIVE_BG, fg=TAB_ACTIVE_FG)
            self.tab_anti.config(bg=TAB_INACTIVE_BG, fg=TAB_INACTIVE_FG)
            self.sub_bar_anti.pack_forget()
            self.sub_bar_codex.pack(fill="x", padx=10, pady=(1, 4), before=self.row_five_h["card"])
        else:
            self.tab_anti.config(bg=TAB_ACTIVE_BG, fg=TAB_ACTIVE_FG)
            self.tab_codex.config(bg=TAB_INACTIVE_BG, fg=TAB_INACTIVE_FG)
            self.sub_bar_codex.pack_forget()
            self.sub_bar_anti.pack(fill="x", padx=9, pady=(1, 4), before=self.row_five_h["card"])
            self.update_anti_pills()

        self.refresh(force_rescan=False)

    def set_anti_group(self, key: str) -> None:
        self.active_anti_key = key
        self.update_anti_pills()
        self.render_anti_view()

    def update_anti_pills(self) -> None:
        for k, btn in self.anti_pills.items():
            if k == self.active_anti_key:
                btn.config(bg=TAB_ACTIVE_BG, fg=TAB_ACTIVE_FG)
            else:
                btn.config(bg=BUTTON_BG, fg=TAB_INACTIVE_FG)

    def set_row_values(
        self,
        row: dict[str, tk.Label | tk.Frame],
        label: str,
        remaining: int | None,
        reset_text: str,
        is_unlimited: bool = False,
    ) -> None:
        row["label"].config(text=label)
        badge = row["reset"]
        rem = row["remaining"]

        if is_unlimited:
            badge.pack_forget()
            rem.config(text=TEXT_UNLIMITED, fg=TEXT_MUTED)
        elif remaining is None:
            badge.pack_forget()
            rem.config(text=TEXT_WAITING, fg=TEXT_WARN)
        else:
            color = get_percent_color(remaining)
            rem.config(text=f"剩余 {remaining}%", fg=color)
            if reset_text and reset_text != "--":
                badge.config(text=reset_text)
                badge.pack(side="right", padx=(0, 6), before=rem)
            else:
                badge.pack_forget()

    def render_codex_view(self) -> None:
        snapshot = self.last_codex_snapshot
        if snapshot is None:
            self.status_label.config(text="● 未找到日志", fg=TEXT_WARN)
            self.set_row_values(self.row_five_h, LABEL_FIVE_HOURS, None, "--")
            self.set_row_values(self.row_weekly, LABEL_ONE_WEEK, None, "--")
            return

        status_text, status_color = format_snapshot_age(snapshot.timestamp)
        self.status_label.config(text=status_text, fg=status_color)

        has_5h = snapshot.five_hour is not None and snapshot.five_hour.used_percent is not None
        has_weekly = snapshot.weekly is not None and snapshot.weekly.used_percent is not None

        if has_5h:
            self.set_row_values(
                self.row_five_h,
                LABEL_FIVE_HOURS,
                snapshot.five_hour.remaining_percent,
                snapshot.five_hour.reset_text,
            )
        else:
            self.set_row_values(self.row_five_h, LABEL_FIVE_HOURS, None, "--", is_unlimited=True)

        if has_weekly:
            self.set_row_values(
                self.row_weekly,
                LABEL_ONE_WEEK,
                snapshot.weekly.remaining_percent,
                snapshot.weekly.reset_text,
            )
        else:
            self.set_row_values(self.row_weekly, LABEL_ONE_WEEK, None, "--", is_unlimited=True)

    def render_anti_view(self) -> None:
        snapshot = self.last_anti_snapshot
        if snapshot is None:
            self.set_row_values(self.row_five_h, LABEL_FIVE_HOURS, None, "--")
            self.set_row_values(self.row_weekly, LABEL_ONE_WEEK, None, "--")
            self.row_five_h["remaining"].config(text="未运行/连接失败", fg=TEXT_WARN)
            self.row_weekly["remaining"].config(text="请确认开启 Anti", fg=TEXT_MUTED)
            return

        group = snapshot.groups.get(self.active_anti_key)
        if not group:
            if snapshot.groups:
                group = next(iter(snapshot.groups.values()))
            else:
                self.set_row_values(self.row_five_h, LABEL_FIVE_HOURS, None, "--")
                self.set_row_values(self.row_weekly, LABEL_ONE_WEEK, None, "--")
                return

        # 5 hour row
        if group.five_hour and group.five_hour.remaining_percent is not None:
            self.set_row_values(
                self.row_five_h,
                LABEL_FIVE_HOURS,
                group.five_hour.remaining_percent,
                group.five_hour.reset_text,
            )
        else:
            self.set_row_values(self.row_five_h, LABEL_FIVE_HOURS, None, "--", is_unlimited=True)

        # Weekly row
        if group.weekly and group.weekly.remaining_percent is not None:
            self.set_row_values(
                self.row_weekly,
                LABEL_ONE_WEEK,
                group.weekly.remaining_percent,
                group.weekly.reset_text,
            )
        else:
            self.set_row_values(self.row_weekly, LABEL_ONE_WEEK, None, "--", is_unlimited=True)

    def refresh(self, force_rescan: bool = False) -> None:
        if self.mode == "codex":
            self.last_codex_snapshot = self.codex_finder.find_latest(force_rescan=force_rescan)
            self.render_codex_view()
        else:
            self.last_anti_snapshot = self.anti_finder.fetch_snapshot()
            self.render_anti_view()


def print_combined_snapshot(codex_home: Path) -> int:
    print("=== Codex Usage Snapshot ===")
    codex_finder = CodexSnapshotFinder(codex_home)
    codex_snap = codex_finder.find_latest()
    if codex_snap is None:
        print("No Codex rate-limit snapshot found.")
    else:
        print(f"source_file={codex_snap.source_file}")
        print(f"updated_at={codex_snap.timestamp.isoformat() if codex_snap.timestamp else 'unknown'}")
        if codex_snap.five_hour and codex_snap.five_hour.used_percent is not None:
            print(f"5h_remaining={codex_snap.five_hour.remaining_percent}%, reset={codex_snap.five_hour.reset_text}")
        else:
            print("5h=(无限制)")
        if codex_snap.weekly and codex_snap.weekly.used_percent is not None:
            print(f"weekly_remaining={codex_snap.weekly.remaining_percent}%, reset={codex_snap.weekly.reset_text}")
        else:
            print("weekly=(无限制)")

    print("\n=== Antigravity Quota Snapshot ===")
    anti_finder = AntigravityQuotaFinder()
    anti_snap = anti_finder.fetch_snapshot()
    if anti_snap is None:
        print("Antigravity is not running or RPC is unreachable.")
    else:
        for key, g in anti_snap.groups.items():
            print(f"[{g.display_name}]")
            if g.five_hour and g.five_hour.remaining_percent is not None:
                print(f"  5h: {g.five_hour.remaining_percent}% (reset: {g.five_hour.reset_text})")
            if g.weekly and g.weekly.remaining_percent is not None:
                print(f"  weekly: {g.weekly.remaining_percent}% (reset: {g.weekly.reset_text})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Always-on-top Codex & Antigravity usage widget")
    parser.add_argument(
        "--mode",
        default="codex",
        choices=("codex", "anti"),
        help="Initial view mode: codex or anti.",
    )
    parser.add_argument(
        "--codex-home",
        default=str(default_codex_home()),
        help="Path to the local Codex home directory. Defaults to %%USERPROFILE%%\\.codex",
    )
    parser.add_argument(
        "--corner",
        default="top-right",
        choices=("top-right", "top-left", "bottom-right", "bottom-left"),
        help="Initial corner for the floating window.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print the latest snapshot once instead of opening the widget.",
    )
    parser.add_argument(
        "--install-startup",
        action="store_true",
        help="Install a user-level autostart script in the Windows Startup folder.",
    )
    parser.add_argument(
        "--remove-startup",
        action="store_true",
        help="Remove the user-level autostart script from the Windows Startup folder.",
    )
    parser.add_argument(
        "--startup-status",
        action="store_true",
        help="Print whether user-level autostart is currently enabled.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    codex_home = Path(args.codex_home).expanduser()

    action_count = sum(
        [
            bool(args.once),
            bool(args.install_startup),
            bool(args.remove_startup),
            bool(args.startup_status),
        ]
    )
    if action_count > 1:
        print("Choose only one of --once, --install-startup, --remove-startup, or --startup-status.")
        return 2

    if args.install_startup:
        print(f"Installed startup stub at: {install_startup()}")
        return 0

    if args.remove_startup:
        print(f"Removed startup stub at: {remove_startup()}")
        return 0

    if args.startup_status:
        print(json.dumps(startup_status_payload(), ensure_ascii=False, indent=2))
        return 0

    if args.once:
        return print_combined_snapshot(codex_home)

    root = tk.Tk()
    UsageWidget(root, codex_home=codex_home, corner=args.corner, initial_mode=args.mode)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
