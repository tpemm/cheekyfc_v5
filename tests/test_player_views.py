from fantrax.analytics.build_player_views import build


def test_player_views_have_unique_player_week_keys():
    weekly, season, manager, position, coverage, report = build()
    assert len(weekly) == len(weekly.drop_duplicates(["fantrax_player_id", "gameweek"]))
    assert len(season) > 0
    assert len(manager) > 0
    assert len(coverage) == 3


def test_actual_position_score_matches_official_export():
    weekly, season, manager, position, coverage, report = build()
    actual = position[position["is_actual_position"]]
    assert ((actual["candidate_position_points"] - actual["official_fantasy_points"]).abs() < 1e-8).all()


def test_waiver_rows_are_not_marked_rescorable():
    weekly, season, manager, position, coverage, report = build()
    waiver = weekly[~weekly["rostered"]]
    assert not waiver["position_rescore_available"].any()
