import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    root: Path
    model_dir: Path
    ml_python: str = ""

    @classmethod
    def environment(cls):
        root = Path(os.getenv("OPENJUTSU_DATA_DIR", Path.home() / ".local/share/openjutsu"))
        return cls(
            root,
            Path(os.getenv("OPENJUTSU_MODEL_DIR", root / "models")),
            os.getenv("OPENJUTSU_ML_PYTHON", ""),
        )

    def initialize(self):
        for name in ("assets", "jobs", "cache"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.model_dir.mkdir(parents=True, exist_ok=True)


class Secrets:
    """Runtime-only configuration; public responses expose readiness, never values."""

    def __init__(self, root: Path):
        self.path = root / "secrets.json"

    def read(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def update(self, key, values):
        data = self.read()
        data[key] = values
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=".secrets-")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
            os.chmod(name, 0o600)
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def redact(self, text):
        for values in self.read().values():
            for key, value in values.items():
                if key in {"api_key", "secret_key", "access_key"} and value:
                    text = text.replace(str(value), "[redacted]")
        return text
