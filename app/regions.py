"""Server identities and isolated profiles; existing Europe data stays in place."""
import json
from pathlib import Path

REGIONS = {
    'europe': dict(label='Europe', host='https://europe.albion-online-data.com', port=34222, server_id=3),
    'west': dict(label='Americas', host='https://west.albion-online-data.com', port=4222, server_id=1),
    'east': dict(label='Asia', host='https://east.albion-online-data.com', port=24222, server_id=2),
}


def region_key(value):
    aliases = {'3':'europe', '1':'west', '2':'east', 'americas':'west', 'asia':'east'}
    key = str(value).lower()
    key = aliases.get(key, key)
    if key not in REGIONS:
        raise ValueError('Unknown Albion server')
    return key


def region_root(base, region):
    base = Path(base)
    key = region_key(region)
    path = base if key == 'europe' else base / 'servers' / key
    path.mkdir(parents=True, exist_ok=True)
    return path


def preferences(base):
    try:
        value = json.loads((Path(base) / 'app_preferences.json').read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_preferences(base, **changes):
    from .preferences import save_settings
    data = preferences(base)
    data.update(changes)
    save_settings(Path(base) / 'app_preferences.json', data)
