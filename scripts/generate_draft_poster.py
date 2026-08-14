"""Generate deterministic completed-draft poster artifacts."""
from pathlib import Path
import pandas as pd
from analytics.draft.poster import save_poster_outputs

ROOT=Path(__file__).resolve().parents[1]

def main() -> None:
    model=ROOT/"data/models/draft_2627"; reports=ROOT/"reports"
    managers=pd.read_csv(model/"draft_manager_grades_2627.csv")
    picks=pd.read_csv(model/"draft_pick_grades_2627.csv")
    save_poster_outputs(managers,picks,reports/"draft_grades_2627_poster.png",reports/"draft_grades_2627_poster.pdf",reports/"draft_grades_2627_poster_audit.csv")
    print("Generated 2400x3200 draft poster PNG, PDF, and audit CSV")

if __name__ == "__main__": main()
