import json
from pathlib import Path
import yaml

BASE_DIR = Path(__file__).resolve().parents[1]


def _resolve(path: str) -> Path:

    """Return an absolute path inside the application package."""

    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = BASE_DIR / candidate
    return candidate


def load_yaml(path: str) -> dict:

    """Charge un fichier YAML et retourne un dictionnaire."""

    target = _resolve(path)

    if not target.exists():
        print(f"File not found at path: {target}")
        return {}

    with target.open('r', encoding='utf-8') as f:
        try:
            data = yaml.safe_load(f)
            return data if data is not None else {}
        except yaml.YAMLError as e:
            print(f"Error parsing YAML file: {e}")
            return {}


def load_json(path: str) -> dict:

    """Charge un fichier json"""

    target = _resolve(path)

    if not target.exists():
        print(f"File not found at path: {target}")
        return {}
    with target.open('r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path: str, data) -> None:

    """Ecrit un fichier json"""

    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)