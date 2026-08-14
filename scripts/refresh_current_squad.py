import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analytics.current_squads.builder import refresh_current_squad

if __name__ == "__main__":
    print(refresh_current_squad("2627"))
