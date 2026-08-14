import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analytics.player_registry.builder import build_from_cache

if __name__ == "__main__":
    print(build_from_cache("2627"))
