"""Read-only bundled assets and writable user data are separate in releases."""
import os
import sys
from pathlib import Path


def resource_root():
    return Path(__file__).resolve().parents[1]


def data_root():
    override = os.environ.get('ALBIONCRAFT_DATA_DIR')
    if override:
        path = Path(override).expanduser().resolve()
    elif getattr(sys, 'frozen', False):
        base = os.environ.get('LOCALAPPDATA')
        path = Path(base) / 'AlbionCraft' if base else Path.home() / '.albioncraft'
    else:
        # Existing source installations retain their settings and databases.
        path = resource_root()
    path.mkdir(parents=True, exist_ok=True)
    return path


def catalog_root(root):
    """Test fixtures can supply their own data; releases use bundled data."""
    root = Path(root)
    return root if (root / 'research/items.json').is_file() else resource_root()
