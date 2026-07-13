import json
import os

_locales = {}
_current = 'ru'


def load_locales():
    """Загрузка всех файлов локализации"""
    locales_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'locales')
    for filename in os.listdir(locales_dir):
        if filename.endswith('.json'):
            lang = filename.replace('.json', '')
            filepath = os.path.join(locales_dir, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                _locales[lang] = json.load(f)


def set_language(lang: str):
    global _current
    if lang in _locales:
        _current = lang


def t(key: str, **kwargs) -> str:
    """Получение перевода по ключу (точечная нотация: 'errors.not_admin')"""
    keys = key.split('.')
    val = _locales.get(_current, {})
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k, key)
        else:
            return key
    if kwargs and isinstance(val, str):
        val = val.format(**kwargs)
    return val
