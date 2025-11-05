from services.file_io import load_json


# Cache des traductions
_translations = {}


def load_translations(lang: str):

    """Charge un fichier de traduction JSON"""

    global _translations

    try:
        _translations[lang] = load_json(f'translations/{lang}.json')

    except FileNotFoundError:
        print(f"Warning: Translation file for language '{lang}' not found.")
        _translations[lang] = {}


def t(key: str, lang: str = "fr") -> str:

    """Retourne la traduction du texte selon la langue"""

    if lang not in _translations:
        load_translations(lang)

    return _translations.get(lang, {}).get(key, key)