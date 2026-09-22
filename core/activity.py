import json
from datetime import datetime
from pathlib import Path


class ActivityLogger:
    """
    Journal local des activités de JARVIS.
    """

    def __init__(
        self,
        file_path,
        max_entries=1000
    ):
        self.file_path = Path(file_path)
        self.max_entries = max_entries

        self.file_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

    def _load(self):

        if not self.file_path.exists():
            return []

        try:

            with open(
                self.file_path,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(file)

            if isinstance(data, list):
                return data

        except (
            json.JSONDecodeError,
            OSError
        ):
            pass

        return []

    def _save(self, entries):

        entries = entries[
            -self.max_entries:
        ]

        with open(
            self.file_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                entries,
                file,
                ensure_ascii=False,
                indent=2
            )

    def log(
        self,
        event,
        message="",
        data=None
    ):

        entries = self._load()

        entry = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "event": event,
            "message": message,
            "data": data or {},
        }

        entries.append(entry)

        self._save(entries)

        return entry

    def recent(self, limit=50):

        entries = self._load()

        return entries[-limit:]

    def clear(self):

        self._save([])

    def count(self):

        return len(self._load())