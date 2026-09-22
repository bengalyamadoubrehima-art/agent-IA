import json
from pathlib import Path


class Memory:
    def __init__(self, file_path):
        self.file = Path(file_path)
        self.file.parent.mkdir(parents=True, exist_ok=True)

        self.data = self._load()

    def _load(self):
        if not self.file.exists():
            return {
                "messages": [],
                "facts": {},
                "preferences": {}
            }

        try:
            return json.loads(
                self.file.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            return {
                "messages": [],
                "facts": {},
                "preferences": {}
            }

    def save(self):
        self.file.write_text(
            json.dumps(
                self.data,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

    def add_message(self, role, content):
        self.data["messages"].append({
            "role": role,
            "content": content
        })

        self.data["messages"] = self.data["messages"][-50:]
        self.save()

    def recent_messages(self, limit=20):
        return self.data["messages"][-limit:]

    def remember(self, key, value):
        self.data["facts"][key] = value
        self.save()
        return f"Information mémorisée : {key}"

    def search(self, query):
        query = query.lower()
        results = []

        for key, value in self.data["facts"].items():
            if query in f"{key} {value}".lower():
                results.append(f"{key} : {value}")

        for key, value in self.data["preferences"].items():
            if query in f"{key} {value}".lower():
                results.append(
                    f"Préférence — {key} : {value}"
                )

        if not results:
            return "Aucune information correspondante."

        return "\n".join(results)
