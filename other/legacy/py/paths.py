"""Repository-owned client and diagnostic locations, independent of cwd."""
from pathlib import Path
import os

ROOT = Path(os.environ.get('GTT_RESOURCE_ROOT', Path(__file__).absolute().parents[1]))
CLIENTS = ROOT / 'clients'
MAHJONG_CLIENT = CLIENTS / 'mahjong-ways2'
BUFFALO_CLIENT = CLIENTS / 'buffalo-win'
MAHJONG_DIAGNOSTICS = ROOT / 'diagnostics/mahjong-ways2'
