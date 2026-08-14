"""Build immutable, deterministic 2026/27 completed-draft grade artifacts."""
from pathlib import Path
import pandas as pd
from analytics.draft.grading import build_all, calibration_audit, freeze_snapshot, position_analysis
from analytics.draft.share import build_share_summary, group_chat_text, share_csv, share_html
from analytics.draft.poster import save_poster_outputs

ROOT=Path(__file__).resolve().parents[1]
SEASON="2627"

def main() -> None:
    draft_path=ROOT/"data/imports/draft/draft_results_2627.csv"
    source=ROOT/"data/models/draft_2627/draft_rankings_2627.csv"
    snapshot=ROOT/"data/snapshots/draft_2627/draft_rankings_draft_day_2627.csv"
    metadata=snapshot.with_suffix(".metadata.json")
    freeze_snapshot(source,snapshot,metadata)
    result=build_all(pd.read_csv(draft_path),pd.read_csv(snapshot))
    quality=ROOT/"data/quality/draft_results_2627"; model=ROOT/"data/models/draft_2627"; reports=ROOT/"reports"
    quality.mkdir(parents=True,exist_ok=True); reports.mkdir(parents=True,exist_ok=True)
    result.validation.to_csv(quality/"draft_results_validation.csv",index=False)
    result.matches.to_csv(quality/"draft_player_match_report.csv",index=False)
    result.matches[~result.matches["Match Status"].eq("Matched")].to_csv(reports/"draft_grades_2627_unresolved_matches.csv",index=False)
    result.canonical.to_csv(model/"draft_results_graded_input_2627.csv",index=False)
    result.picks.to_csv(model/"draft_pick_grades_2627.csv",index=False)
    result.managers.to_csv(model/"draft_manager_grades_2627.csv",index=False)
    result.categories.to_csv(model/"draft_category_scores_2627.csv",index=False)
    result.awards.to_csv(model/"draft_awards_2627.csv",index=False)
    positions = position_analysis(result.picks)
    positions.to_csv(model/"draft_position_grades_2627.csv", index=False)
    result.managers.to_csv(reports/"draft_grades_2627_manager_rankings.csv",index=False)
    result.picks.to_csv(reports/"draft_grades_2627_pick_grades.csv",index=False)
    result.awards.to_csv(reports/"draft_grades_2627_awards.csv",index=False)
    result.categories.to_csv(reports/"draft_grades_2627_category_scores.csv",index=False)
    positions.to_csv(reports/"draft_grades_2627_position_grades.csv", index=False)
    calibration_audit(result.managers, result.categories).to_csv(
        reports/"draft_grades_2627_calibration_audit.csv", index=False
    )
    share = build_share_summary(result.managers, result.picks)
    (reports/"draft_grades_2627_share.csv").write_bytes(share_csv(share))
    (reports/"draft_grades_2627_share.html").write_text(share_html(share), encoding="utf-8")
    (reports/"draft_grades_2627_group_chat.txt").write_text(group_chat_text(share, result.awards),encoding="utf-8")
    save_poster_outputs(result.managers, result.picks, reports/"draft_grades_2627_poster.png", reports/"draft_grades_2627_poster.pdf", reports/"draft_grades_2627_poster_audit.csv")
    print(f"Built {len(result.picks)} pick grades and {len(result.managers)} manager grades; unresolved=0")

if __name__ == "__main__": main()
