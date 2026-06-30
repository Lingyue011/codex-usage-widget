from __future__ import annotations

import argparse
import json
import os
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


MAX_CANDIDATE_FILES = 24
MAX_TAIL_BYTES = 256 * 1024
WINDOW_WIDTH = 252
WINDOW_HEIGHT = 116
WINDOW_MARGIN = 10

CARD_BG = "#F7F2EA"
CARD_BORDER = "#D9CCBC"
ROW_BG = "#FCF9F4"
ROW_BORDER = "#E7DCCE"
TEXT_PRIMARY = "#2E2720"
TEXT_SECONDARY = "#887968"
TEXT_ACCENT = "#0F815A"
TEXT_WARN = "#B36A18"
BUTTON_BG = "#EFE5D7"
BUTTON_ACTIVE = "#E5D8C7"
BADGE_BG = "#E7F4ED"
BADGE_WARN_BG = "#F7EBD8"
BADGE_TEXT = "#0F815A"
BADGE_WARN_TEXT = "#B36A18"

LABEL_FIVE_HOURS = "5 \u5c0f\u65f6"
LABEL_ONE_WEEK = "1 \u5468"
TEXT_WAITING = "\u7b49\u5f85"
TEXT_STALE = "\u6ede\u540e"


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


def local_reset_text(unix_seconds: int | None) -> str:
    if not unix_seconds:
        return "--"
    reset_dt = datetime.fromtimestamp(unix_seconds, tz=timezone.utc).astimezone()
    now = datetime.now().astimezone()
    if reset_dt.date() == now.date():
        return reset_dt.strftime("%H:%M")
    if reset_dt.year == now.year:
        return f"{reset_dt.month}\u6708{reset_dt.day}\u65e5"
    return reset_dt.strftime("%Y-%m-%d")


def debug_reset_text(unix_seconds: int | None) -> str:
    if not unix_seconds:
        return "--"
    reset_dt = datetime.fromtimestamp(unix_seconds, tz=timezone.utc).astimezone()
    return reset_dt.strftime("%Y-%m-%d %H:%M")


def clamp_percent(value: float | int | None) -> int | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    numeric = max(0.0, min(100.0, numeric))
    return int(round(numeric))


def iter_tail_lines(path: Path, max_bytes: int = MAX_TAIL_BYTES) -> Iterable[str]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        handle.seek(max(0, size - max_bytes))
        block = handle.read()
    for raw_line in reversed(block.splitlines()):
        yield raw_line.decode("utf-8", errors="replace").strip()


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
        return local_reset_text(self.resets_at)


@dataclass
class UsageSnapshot:
    source_file: Path
    timestamp: datetime | None
    primary: LimitWindow
    secondary: LimitWindow

    @property
    def is_stale(self) -> bool:
        if self.timestamp is None:
            return True
        age = datetime.now(timezone.utc) - self.timestamp.astimezone(timezone.utc)
        return age.total_seconds() > 20 * 60


def parse_limit_window(payload: dict) -> LimitWindow:
    return LimitWindow(
        used_percent=clamp_percent(payload.get("used_percent")),
        window_minutes=payload.get("window_minutes"),
        resets_at=payload.get("resets_at"),
    )


def extract_snapshot_from_file(path: Path) -> UsageSnapshot | None:
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
            primary = parse_limit_window(rate_limits.get("primary") or {})
            secondary = parse_limit_window(rate_limits.get("secondary") or {})
            return UsageSnapshot(
                source_file=path,
                timestamp=parse_timestamp(item.get("timestamp")),
                primary=primary,
                secondary=secondary,
            )
    except OSError:
        return None
    return None


class SnapshotFinder:
    def __init__(self, codex_home: Path) -> None:
        self.codex_home = codex_home
        self.sessions_root = codex_home / "sessions"
        self.current_file: Path | None = None
        self.cached_candidates: list[Path] = []
        self.last_scan_at = 0.0

    def candidate_files(self, force_rescan: bool = False) -> list[Path]:
        now = time.monotonic()
        if self.cached_candidates and not force_rescan and now - self.last_scan_at < 3600:
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

    def find_latest(self, force_rescan: bool = False) -> UsageSnapshot | None:
        candidates: list[Path] = []
        if self.current_file is not None and self.current_file.exists():
            candidates.append(self.current_file)
        for path in self.candidate_files(force_rescan=force_rescan):
            if path not in candidates:
                candidates.append(path)

        freshest: UsageSnapshot | None = None
        for path in candidates:
            snapshot = extract_snapshot_from_file(path)
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


class UsageWidget:
    def __init__(self, root: tk.Tk, codex_home: Path, corner: str) -> None:
        self.root = root
        self.corner = corner
        self.finder = SnapshotFinder(codex_home)
        self.drag_offset_x = 0
        self.drag_offset_y = 0

        self.root.title("Codex Usage Widget")
        self.root.configure(bg=CARD_BG)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.97)

        self.outer = tk.Frame(
            self.root,
            bg=CARD_BG,
            highlightbackground=CARD_BORDER,
            highlightthickness=1,
            bd=0,
        )
        self.outer.pack(fill="both", expand=True)

        self.header = tk.Frame(self.outer, bg=CARD_BG)
        self.header.pack(fill="x", padx=8, pady=(6, 4))
        self.header.bind("<ButtonPress-1>", self.start_drag)
        self.header.bind("<B1-Motion>", self.on_drag)

        self.refresh_button = self.make_icon_button("\u21bb", lambda _event: self.refresh(force_rescan=True))
        self.refresh_button.pack(side="right", padx=(0, 4))

        self.close_button = self.make_icon_button("\u00d7", lambda _event: self.root.destroy())
        self.close_button.pack(side="right")

        self.primary_row = self.make_row(LABEL_FIVE_HOURS)
        self.secondary_row = self.make_row(LABEL_ONE_WEEK)

        self.root.update_idletasks()
        self.place_in_corner()
        self.refresh(force_rescan=True)

    def make_icon_button(self, text: str, on_click) -> tk.Label:
        button = tk.Label(
            self.header,
            text=text,
            bg=BUTTON_BG,
            fg=TEXT_PRIMARY,
            font=("Segoe UI Symbol", 8, "bold"),
            width=2,
            cursor="hand2",
            padx=1,
            pady=0,
        )
        button.bind("<Button-1>", on_click)
        button.bind("<Enter>", lambda _event: button.config(bg=BUTTON_ACTIVE))
        button.bind("<Leave>", lambda _event: button.config(bg=BUTTON_BG))
        return button

    def make_row(self, label_text: str) -> dict[str, tk.Label]:
        card = tk.Frame(
            self.outer,
            bg=ROW_BG,
            highlightbackground=ROW_BORDER,
            highlightthickness=1,
            bd=0,
        )
        card.pack(fill="x", padx=8, pady=(0, 4))

        row = tk.Frame(card, bg=ROW_BG)
        row.pack(fill="x", padx=8, pady=5)

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
            font=("Segoe UI", 10, "bold"),
        )
        remaining.pack(side="right")

        reset = tk.Label(
            row,
            text="--",
            bg=BUTTON_BG,
            fg=TEXT_SECONDARY,
            anchor="e",
            font=("Segoe UI", 8, "bold"),
            padx=6,
            pady=1,
        )
        reset.pack(side="right", padx=(0, 6))

        return {"label": label, "remaining": remaining, "reset": reset}

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

    def start_drag(self, event: tk.Event) -> None:
        self.drag_offset_x = event.x_root - self.root.winfo_x()
        self.drag_offset_y = event.y_root - self.root.winfo_y()

    def on_drag(self, event: tk.Event) -> None:
        x = event.x_root - self.drag_offset_x
        y = event.y_root - self.drag_offset_y
        self.root.geometry(f"+{x}+{y}")

    def set_status(self, text: str, fresh: bool) -> None:
        return

    def set_row(self, row: dict[str, tk.Label], remaining: int | None, reset_text: str) -> None:
        if remaining is None:
            row["remaining"].config(text=TEXT_WAITING, fg=TEXT_WARN)
            row["reset"].config(text="--")
            return

        color = TEXT_ACCENT if remaining >= 20 else TEXT_WARN
        row["remaining"].config(text=f"\u5269\u4f59 {remaining}%", fg=color)
        row["reset"].config(text=reset_text)

    def refresh(self, force_rescan: bool = False) -> None:
        snapshot = self.finder.find_latest(force_rescan=force_rescan)
        if snapshot is None:
            self.set_status(TEXT_WAITING, fresh=False)
            self.set_row(self.primary_row, None, "--")
            self.set_row(self.secondary_row, None, "--")
        else:
            self.set_row(
                self.primary_row,
                snapshot.primary.remaining_percent,
                snapshot.primary.reset_text,
            )
            self.set_row(
                self.secondary_row,
                snapshot.secondary.remaining_percent,
                snapshot.secondary.reset_text,
            )
            self.set_status(TEXT_STALE if snapshot.is_stale else "", fresh=not snapshot.is_stale)


def print_snapshot(snapshot: UsageSnapshot | None) -> int:
    if snapshot is None:
        print("No Codex rate-limit snapshot found.")
        return 1

    print(f"source_file={snapshot.source_file}")
    print(f"updated_at={snapshot.timestamp.isoformat() if snapshot.timestamp else 'unknown'}")
    print(f"primary_used={snapshot.primary.used_percent}")
    print(f"primary_remaining={snapshot.primary.remaining_percent}")
    print(f"primary_reset={debug_reset_text(snapshot.primary.resets_at)}")
    print(f"secondary_used={snapshot.secondary.used_percent}")
    print(f"secondary_remaining={snapshot.secondary.remaining_percent}")
    print(f"secondary_reset={debug_reset_text(snapshot.secondary.resets_at)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Always-on-top Codex usage widget")
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
    return parser


def main() -> int:
    args = build_parser().parse_args()
    codex_home = Path(args.codex_home).expanduser()

    finder = SnapshotFinder(codex_home)
    if args.once:
        return print_snapshot(finder.find_latest())

    root = tk.Tk()
    UsageWidget(root, codex_home=codex_home, corner=args.corner)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
