from fantrax.analytics.optimizer import LineupPlayer, optimize_lineup
from fantrax.analytics.scoring_engine import score_player_positions


def test_actual_position_is_official_score():
    result = score_player_positions(
        official_points=10.5, actual_position="M", eligible_positions="D,M",
        goals=0, assists=0, clean_sheets=1, goals_against=0,
    )
    assert result.scores_by_position["M"] == 10.5
    assert result.scores_by_position["D"] == 15.5


def test_waiver_row_is_not_cross_position_rescored():
    result = score_player_positions(
        official_points=12, actual_position="", eligible_positions="D,M",
        goals=None, assists=None, clean_sheets=None, goals_against=None,
        full_stats_available=False,
    )
    assert not result.rescore_available
    assert result.scoring_source == "official_export_only"


def test_optimizer_builds_legal_eleven_and_uses_multi_position_score():
    players = []
    row = 0
    for _ in range(1):
        players.append(LineupPlayer(row, f"g{row}", "G", {"G": 5})); row += 1
    for _ in range(3):
        players.append(LineupPlayer(row, f"d{row}", "D", {"D": 5})); row += 1
    for _ in range(2):
        players.append(LineupPlayer(row, f"m{row}", "M", {"M": 5})); row += 1
    for _ in range(1):
        players.append(LineupPlayer(row, f"f{row}", "F", {"F": 5})); row += 1
    # Four flexible players complete a legal XI; one is worth more as D.
    players.extend([
        LineupPlayer(row, "x1", "X1", {"D": 12, "M": 7}),
        LineupPlayer(row+1, "x2", "X2", {"M": 9, "F": 6}),
        LineupPlayer(row+2, "x3", "X3", {"D": 8, "F": 8}),
        LineupPlayer(row+3, "x4", "X4", {"M": 8, "F": 8}),
    ])
    result = optimize_lineup(players)
    assert result.legal_solution_found
    assert len(result.assignments) == 11
    assert result.assignments[row] == "D"
