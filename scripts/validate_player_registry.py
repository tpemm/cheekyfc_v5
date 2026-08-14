import pandas as pd
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.project_paths import PROJECT_ROOT

if __name__ == "__main__":
    path = PROJECT_ROOT / "data/reference/player_registry_2627.csv"
    frame = pd.read_csv(path, low_memory=False)
    assert frame["registry_player_id"].is_unique
    active = frame[frame["active_epl"].fillna(False)]
    assert not active["fpl_player_id"].dropna().duplicated().any()
    assert frame["registry_status"].notna().all()
    print(f"Validated {len(frame)} registry rows.")
