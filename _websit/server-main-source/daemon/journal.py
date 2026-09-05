# -*- coding: utf-8 -*-
"""Append-only ticket journal: write-before-side-effect, idempotent replay on restart."""

import json
import os
import tempfile
from pathlib import Path


class Journal:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen_event_ids = set()

    def append(self, event: dict) -> None:
        event = dict(event)
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        # atomic-ish append: write+flush+fsync keeps crash recovery honest
        fd = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        if event.get("type") == "feishu_event" and event.get("event_id"):
            self._seen_event_ids.add(event["event_id"])

    def load_events(self) -> list:
        events = []
        if not self.path.exists():
            return events
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                continue  # torn tail write: skip, journal is advisory state
        return events

    def seen_event(self, event_id: str) -> bool:
        return event_id in self._seen_event_ids

    def prime_seen_events(self, events=None) -> None:
        for event in events if events is not None else self.load_events():
            if event.get("type") == "feishu_event" and event.get("event_id"):
                self._seen_event_ids.add(event["event_id"])


def spool_dir(base: Path) -> Path:
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_spool(path: Path, payload: dict) -> None:
    """Persist an unprocessed event to survive restart (best-effort replay input)."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(dir=str(path), suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        target = path / f"{payload.get('event_id', Path(tmp).stem)}.json"
        os.replace(tmp, target)
    except Exception:
        pass


def list_spool(path: Path) -> list:
    items = []
    for file in sorted(Path(path).glob("*.json")):
        try:
            items.append(json.loads(file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return items


def clear_spool(path: Path, event_id: str) -> None:
    try:
        (Path(path) / f"{event_id}.json").unlink(missing_ok=True)
    except OSError:
        pass
