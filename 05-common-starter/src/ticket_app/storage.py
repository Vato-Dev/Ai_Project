import sqlite3
from pathlib import Path

from ticket_app.analysis_models import Record


class Store:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS analyses (id TEXT PRIMARY KEY, payload TEXT)")

    def save(self, record: Record):
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT INTO analyses VALUES (?, ?)", (record.id, record.model_dump_json())
            )

    def recent(self):
        with sqlite3.connect(self.path) as conn:
            return [
                Record.model_validate_json(row[0])
                for row in conn.execute("SELECT payload FROM analyses ORDER BY rowid DESC LIMIT 20")
            ]
