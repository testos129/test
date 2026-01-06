import json
import os
import yaml

from services.logging_setup import get_logger

logger = get_logger('default')


def load_yaml(path: str) -> dict:

    """Charge un fichier YAML et retourne un dictionnaire."""
    
    if not os.path.exists(path):
        logger.warning(f"File not found at path: {path}")
        return {}
    
    with open(path, 'r', encoding='utf-8') as f:
        try:
            data = yaml.safe_load(f)
            return data if data is not None else {}
        except yaml.YAMLError as e:
            logger.warning(f"Error loading yaml file for path {path}: {e}")
            return {}


def load_json(path: str) -> dict:

    """Charge un fichier json"""

    if not os.path.exists(path):
        print(f"File not found at path: {os.path}")
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path: str, data) -> None:
    
    """Ecrit un fichier json"""
    
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)