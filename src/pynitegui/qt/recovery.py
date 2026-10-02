"""Atomic, per-window recovery snapshots; never writes the actual project file."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

from .model import Project


class RecoveryStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / f"{uuid.uuid4().hex}.json"
        self.errors = []

    def write(self, project, saved, original_path=None):
        project.validate()
        payload = {"format": "pynitegui-recovery-1", "pid": os.getpid(),
                   "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "original_path": str(original_path) if original_path else None,
                   "project": project.to_dict(), "saved": saved}
        temporary = self.path.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def clear(self):
        self.path.unlink(missing_ok=True)

    @staticmethod
    def read(path):
        with Path(path).open(encoding="utf-8") as stream:
            payload = json.load(stream)
        if not isinstance(payload, dict) or payload.get("format") != "pynitegui-recovery-1":
            raise ValueError("Unknown recovery format.")
        if not isinstance(payload.get("updated_at"), str):
            raise ValueError("Invalid recovery timestamp.")
        datetime.fromisoformat(payload["updated_at"])
        if not isinstance(payload.get("project"), dict) or not isinstance(payload.get("saved"), dict):
            raise ValueError("Invalid recovery project data.")
        original = payload.get("original_path")
        if original is not None and not isinstance(original, str):
            raise ValueError("Invalid recovered project path.")
        try:
            project = Project.from_dict(payload["project"])
            saved = Project.from_dict(payload["saved"]).to_dict()
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError("Malformed recovery project data.") from error
        return project, Path(original) if original else None, saved

    def snapshots(self, include_active=False):
        snapshots = []
        self.errors = []
        for path in self.directory.glob("*.json"):
            try:
                self.read(path)
                with path.open(encoding="utf-8") as stream:
                    payload = json.load(stream)
                pid = payload.get("pid")
                active = False
                if type(pid) is int and pid > 0:
                    try:
                        os.kill(pid, 0)
                        active = True
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        active = True
                if include_active or not active:
                    snapshots.append((path, payload))
            except (OSError, ValueError, TypeError, KeyError) as error:
                self.errors.append((path, str(error)))
        return sorted(snapshots, key=lambda item: item[1]["updated_at"], reverse=True)
