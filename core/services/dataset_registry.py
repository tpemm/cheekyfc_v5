"""Logical dataset catalog for the Fantrax analytics platform.

This module intentionally has no data-loading or filesystem responsibilities.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from core.models.dataset_definition import DatasetDefinition


class RegistryValidationError(ValueError):
    """Raised when dataset definitions do not form a valid registry."""


_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def _definition(
    key: str,
    display_name: str,
    description: str,
    classification: str,
    namespace: str,
    filename_template: str,
    *,
    producer: str | None,
    consumers: tuple[str, ...],
    aliases: tuple[str, ...] = (),
    required: bool = True,
    cacheable: bool = True,
    mutable: bool = True,
    schema_name: str | None = None,
    working_subdirectory: str | None = None,
    snapshot_subdirectory: str | None = None,
    required_columns: tuple[str, ...] = (),
    family: bool = False,
) -> DatasetDefinition:
    default_directories = {
        "processed": "processed",
        "analytics": "analytics_views",
        "reference": "reference",
        "draft": "models/draft_{season_id}",
    }
    default_directory = default_directories.get(namespace, "")
    return DatasetDefinition(
        key=key,
        display_name=display_name,
        description=description,
        classification=classification,
        namespace=namespace,
        filename_template=filename_template,
        required=required,
        producer=producer,
        consumers=consumers,
        aliases=aliases,
        cacheable=cacheable,
        mutable=mutable,
        schema_name=schema_name,
        working_subdirectory=(
            default_directory
            if working_subdirectory is None
            else working_subdirectory
        ),
        snapshot_subdirectory=(
            default_directory
            if snapshot_subdirectory is None
            else snapshot_subdirectory
        ),
        required_columns=required_columns,
        family=family,
    )


CORE_DATASETS: tuple[DatasetDefinition, ...] = (
    _definition(
        "premier_league_clubs", "Premier League Clubs",
        "Canonical 2026/27 Premier League club identities and explicit provider mappings.",
        "reference", "reference", "premier_league_clubs_{season_id}.csv",
        producer="scripts.build_team_fixture_foundation", consumers=("Teams", "Players", "fixture pipeline"),
        required=False, schema_name=None, required_columns=("canonical_club_id", "canonical_name", "abbreviation", "fantrax_code"),
    ),
    _definition(
        "team_matches", "Canonical Team Matches",
        "One provider-neutral row per known match, including competition and Fantrax period context.",
        "model", "season", "team_matches_{season_id}.csv",
        producer="scripts.build_team_fixture_foundation", consumers=("Teams", "Players", "fixture pipeline"),
        required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
        required_columns=("match_id", "competition_type", "home_club_id", "away_club_id", "kickoff_time"),
    ),
    _definition(
        "team_fixtures", "Team Fixtures",
        "Canonical matches oriented once from each club's perspective.",
        "model", "season", "team_fixtures_{season_id}.csv",
        producer="scripts.build_team_fixture_foundation", consumers=("Teams", "Players"),
        required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
        required_columns=("club_id", "match_id", "opponent_id", "home_away", "kickoff_time"),
    ),
    _definition(
        "club_elo_current", "Current Club Elo",
        "Latest soccerdata ClubElo ratings mapped to canonical current Premier League clubs.",
        "model", "season", "club_elo_current_{season_id}.csv", producer="scripts.refresh_soccerdata_team_context",
        consumers=("Teams", "Players", "fixture intelligence"), required=False, schema_name=None,
        working_subdirectory="models/season_{season_id}", required_columns=("canonical_club_id","club","elo","elo_rank_pl"),
    ),
    _definition(
        "club_elo_history", "Club Elo History",
        "Cached historical ClubElo time series for canonical Premier League clubs.",
        "model", "season", "club_elo_history_{season_id}.csv", producer="scripts.refresh_soccerdata_team_context",
        consumers=("Teams", "fixture intelligence"), required=False, schema_name=None,
        working_subdirectory="models/season_{season_id}", required_columns=("canonical_club_id","date","elo"),
    ),
    _definition("player_pitch_events","Historical Player Pitch Events","Compact Parquet event activity for production pitch filtering.","model","season","player_pitch_events_{season_id}.parquet",producer="scripts.build_advanced_descriptive_products",consumers=("Player Pitch",),required=False,schema_name=None,working_subdirectory="models/season_{season_id}/advanced",required_columns=("canonical_match_id","canonical_player_id","event_type","x","y")),
    *(
        _definition(key,label,description,"model","season",f"{key}_{{season_id}}.csv",producer="scripts.build_team_analytics_2627",consumers=("Teams","team research","matchup analytics"),required=False,schema_name=None,working_subdirectory="models/season_{season_id}",required_columns=required_columns)
        for key,label,description,required_columns in (
            ("team_match_analytics","Canonical Team Match Analytics","One observed row per club and completed Premier League match.",("canonical_match_id","club_id","opponent_id","manager_id","formation","xg","xga","feature_class")),
            ("team_season_profile","Team Season Profile","Descriptive season aggregates with neutral league volume context.",("club_id","matches","feature_class")),
            ("team_manager_profile","Team Manager Regime Profile","Observed team aggregates by match-observed manager regime.",("club_id","manager_id","matches","feature_class")),
            ("team_formation_analytics","Team Formation Analytics","Observed team aggregates by starting formation.",("club_id","formation","matches","formation_share","feature_class")),
            ("team_home_away_profile","Team Home Away Profile","Canonical fixture-oriented venue splits.",("club_id","home_away","matches","feature_class")),
            ("team_fantasy_allowed_match","Team Fantasy Allowed Match","Match-attributable best-available fantasy observations allowed by opponent.",("canonical_match_id","club_id","fantasy_points_allowed","feature_class")),
            ("team_fantasy_allowed_position_match","Team Positional Fantasy Allowed Match","Match-attributable fantasy observations allowed by primary Fantrax position.",("canonical_match_id","club_id","position_group","fantasy_points_allowed","feature_class")),
        )
    ),
    *(
        _definition(key,label,description,"model","season",f"{key}_{{season_id}}.csv",producer="scripts.build_team_tactical_99c",consumers=consumers,required=False,schema_name=None,working_subdirectory="models/season_{season_id}",required_columns=required_columns)
        for key,label,description,consumers,required_columns in (
            ("team_tactical_match_features","Team Tactical Match Features","Observed match-level tactical rates and spatial features calibrated by team_tactical_v1.",( "Teams","Player Role & Tactical","Fantasy Allowed"),("season","canonical_match_id","club_id","opponent_id","methodology_version")),
            ("team_tactical_profile","Team Tactical Profile","Club-season tactical dimensions, percentiles, transparent traits, and sample confidence.",( "Teams","opponent context"),("club_id","matches","confidence","methodology_version")),
            ("team_manager_tactical_profile","Team Manager Tactical Profile","Match-observed manager-regime tactical summaries with sample gating.",( "Teams",),("club_id","manager_id","matches","confidence","methodology_version")),
            ("team_formation_tactical_profile","Team Formation Tactical Profile","Observed formation tactical summaries without causal claims.",( "Teams",),("club_id","formation","matches","confidence","methodology_version")),
            ("team_venue_tactical_profile","Team Venue Tactical Profile","Observed home/away tactical summaries.",( "Teams","matchup analytics"),("club_id","home_away","matches","confidence","methodology_version")),
            ("team_opponent_tactical_context","Team Opponent Tactical Context","Joinable match/opponent tactical fingerprint for Player and Fantasy Allowed research.",( "Players","Fantasy Allowed","team matchup analytics"),("canonical_match_id","club_id","opponent_id","methodology_version")),
        )
    ),
    *(
        _definition(key,label,description,"model","season",f"{key}_{{season_id}}.csv",
            producer="scripts.build_team_matchup_foundation",consumers=consumers,required=False,schema_name=None,
            working_subdirectory="models/season_{season_id}",required_columns=required_columns)
        for key,label,description,consumers,required_columns in (
            ("team_match_observations","Team Match Observations","Observed team-perspective match facts with source coverage.",( "Teams","matchup analytics"),("match_id","club_id","opponent_id","feature_class")),
            ("team_position_fantasy_allowed","Team Position Fantasy Allowed","Derived opponent fantasy production allowed by canonical position and transparent window.",( "Teams","Players","matchup analytics"),("club_id","position_group","window","matches_observed","feature_class")),
            ("team_attack_profile","Team Attack Profile","Transparent observed/derived attacking rates.",( "Teams","matchup analytics"),("club_id","matches_observed","feature_class")),
            ("team_defense_profile","Team Defense Profile","Transparent observed/derived defensive and allowed rates.",( "Teams","matchup analytics"),("club_id","matches_observed","feature_class")),
            ("team_matchup_features","Team Matchup Features","Model-ready future team fixture features without predictions.",( "matchup analytics",),("club_id","opponent_id","match_id","feature_class")),
            ("player_matchup_features","Player Matchup Features","Model-ready player/opponent features without projections.",( "Players","matchup analytics"),("fantrax_player_id","club_id","position_group","feature_class","contains_prediction")),
        )
    ),
    *(
        _definition(key,label,description,"model","season",f"{key}_{{season_id}}.csv",
            producer="scripts.build_whoscored_scale_products",consumers=("Operations Center","advanced analytics"),
            required=False,schema_name=None,working_subdirectory="models/season_{season_id}",required_columns=required_columns)
        for key,label,description,required_columns in (
            ("whoscored_match_scale","WhoScored Match Scale","Staged normalized WhoScored matches.",("canonical_match_id","whoscored_match_id")),
            ("whoscored_team_match_scale","WhoScored Team Match Scale","Manager-aware team-match observations.",("canonical_match_id","club_id","manager_id")),
            ("whoscored_lineup_scale","WhoScored Lineup Scale","Observed lineups, roles, formations, and ratings.",("canonical_match_id","whoscored_player_id","club_id")),
            ("whoscored_event_scale","WhoScored Event Scale","Canonical unique event activity with provider IDs retained.",("canonical_match_id","event_id","provider_event_id")),
            ("advanced_player_match_scale","Advanced Player Match Scale","Staged provider-enriched player-match observations.",("canonical_match_id","canonical_player_id","feature_class")),
            ("player_tactical_position_history_scale","Player Tactical Position History","Observed manager-aware tactical role shares.",("canonical_player_id","manager_id","position_share")),
            ("team_formation_history_scale","Team Formation History","Observed manager-aware formation shares.",("club_id","manager_id","formation_share")),
            ("team_event_features_scale","Team Event Features","Transparent observed and spatial team-match components.",("canonical_match_id","club_id","feature_class")),
            ("player_event_activity_scale","Player Event Activity","Reusable event activity, explicitly not tracking data.",("canonical_match_id","event_id","dataset_label")),
        )
    ),
    _definition(
        "refresh_status","Refresh Status","Evidence-derived Core, advanced, schedule, model, and quality freshness status.",
        "quality","season", "refresh_status_{season_id}.csv",producer="scripts.build_refresh_status",consumers=("Operations Center",),
        required=False,schema_name=None,working_subdirectory="quality/season_{season_id}",required_columns=("area","state","last_successful_refresh","coverage","detail"),
    ),
    _definition(
        "weekly_advanced_refresh_latest","Current Advanced Refresh Status","Incremental commissioner-only WhoScored plan and coverage evidence.",
        "quality","season","weekly_advanced_refresh_latest.json",producer="scripts.weekly_advanced_refresh",consumers=("Operations Center",),
        required=False,schema_name=None,working_subdirectory="quality/season_{season_id}",required_columns=(),
    ),
    _definition(
        "historical_player_research_profile","Historical Player Research Profile","Compact best-available prior-season display metrics with provenance.",
        "model","season","historical_player_research_profile_2526.csv",producer="scripts.build_historical_player_research_profile",consumers=("Players",),
        required=False,schema_name=None,working_subdirectory="models/season_2627",required_columns=("canonical_player_id","starts","tackles_won_per_start"),
    ),
    *(
        _definition(key,label,description,"model","season",f"{key}_{{season_id}}.csv",
            producer="scripts.build_whoscored_season_products",consumers=("future Player/Teams advanced UI","historical modeling"),required=False,schema_name=None,
            working_subdirectory="models/season_{season_id}/advanced",required_columns=required_columns)
        for key,label,description,required_columns in (
            ("whoscored_match","WhoScored Historical Matches","Validated supplemental season match observations.",("canonical_match_id","whoscored_match_id")),
            ("whoscored_lineup","WhoScored Historical Lineups","Validated supplemental season lineups and tactical roles.",("canonical_match_id","whoscored_player_id","club_id")),
            ("whoscored_event","WhoScored Historical Events","Validated season event activity with canonical unique keys.",("canonical_match_id","event_id","provider_event_id")),
            ("advanced_player_match","Advanced Historical Player Match","Supplemental WhoScored, Understat, and safely attributed Fantrax observations.",("canonical_match_id","canonical_player_id","feature_class")),
            ("player_match_roles","Historical Player Match Roles","Observed starting tactical roles with manager and formation context.",("canonical_match_id","canonical_player_id","manager_id")),
            ("player_role_profile","Historical Player Role Profiles","Observed role shares by player, manager, and formation.",("canonical_player_id","actual_position_standardized","role_share")),
            ("team_formation_history","Historical Team Formation History","One observed formation per club-match.",("canonical_match_id","club_id","manager_id","formation")),
            ("team_formation_profile","Historical Team Formation Profiles","Formation usage by club, manager, and venue.",("club_id","manager_id","formation","formation_share")),
            ("team_match_features","Historical Team Match Features","Transparent event and spatial team-match components.",("canonical_match_id","club_id","feature_class")),
            ("player_event_data","Historical Player Event Activity","Pitch-view-ready event activity, not tracking data.",("canonical_match_id","event_id","dataset_label")),
            ("historical_position_fantasy_allowed","Historical Positional Fantasy Allowed","Single-primary-position opponent baseline using exact Fantrax attribution only.",("opponent_id","position_group","position_method")),
            ("supplemental_player_match","Supplemental Player Match","Fantrax-first, provenance-retaining historical advanced player-match facts.",("canonical_match_id","canonical_player_id","key_passes_source")),
            ("player_advanced_profile","Player Advanced Profile","Historical totals and transparent rate denominators.",("canonical_player_id","appearances","starts")),
            ("player_role_usage","Player Role Usage","Observed tactical-role starts by player, manager, and formation.",("canonical_player_id","manager_id","actual_tactical_role","role_share")),
            ("player_set_piece_usage","Player Set Piece Usage","Observed set-piece attempts, shares, and ranks by window and manager regime.",("canonical_player_id","club_id","set_piece_type","window","rank")),
            ("team_set_piece_hierarchy","Team Set Piece Hierarchy","Evidence-backed set-piece hierarchy with shares and samples.",("club_id","set_piece_type","window","rank","role_label")),
            ("team_playstyle_profile","Team Playstyle Profile","Observed manager/formation event rates without a composite score.",("club_id","manager_id","formation","matches")),
            ("historical_fantasy_allowed_ranked","Historical Fantasy Allowed Ranked","Fantrax-authoritative positional production allowed with ranks.",("opponent_id","position_group","matches")),
            ("formation_player_usage","Formation Player Usage","Observed formation-role player usage.",("club_id","manager_id","formation","actual_tactical_role","role_rank")),
        )
    ),
    *(
        _definition(key,label,description,"model","season",f"{key}_{{season_id}}.csv",
            producer="scripts.build_whoscored_historical_poc",consumers=("advanced match POC",),
            required=False,schema_name=None,working_subdirectory="models/season_{season_id}",required_columns=required_columns)
        for key,label,description,required_columns in (
            ("whoscored_match_poc","WhoScored Match POC","Observed normalized WhoScored match facts for the bounded historical POC.",("canonical_match_id","whoscored_match_id","source")),
            ("whoscored_lineup_poc","WhoScored Lineup POC","Observed WhoScored lineup, role, rating, and formation facts.",("canonical_match_id","whoscored_player_id","club_id","source")),
            ("whoscored_event_poc","WhoScored Event POC","Observed WhoScored event stream with raw qualifier preservation.",("canonical_match_id","event_id","event_type","source")),
            ("advanced_player_match_poc","Advanced Player Match POC","Identity-safe sample player-match joins across Fantrax, Understat, and WhoScored.",("canonical_match_id","canonical_player_id","feature_class","contains_prediction")),
            ("team_formation_usage_poc","Team Formation Usage POC","Sample-only observed starting formation frequencies.",("club_id","formation","matches_observed","scope")),
            ("player_role_usage_poc","Player Role Usage POC","Sample-only mapped player starting-role frequencies.",("canonical_player_id","club_id","actual_position_standardized","scope")),
        )
    ),
    _definition(
        "master_player_weekly",
        "Master Player Weekly",
        "Canonical player-by-gameweek table combining Fantrax and Understat data.",
        "processed",
        "processed",
        "master_player_weekly_{season_id}.csv",
        producer="fantrax.analytics.core.build_master_weekly",
        consumers=("manager analytics", "player analytics", "draft analytics"),
        aliases=("master_weekly",),
        schema_name="master_player_weekly",
    ),
    _definition(
        "manager_player_weekly",
        "Manager Player Weekly",
        "Player-week facts enriched with manager ownership and lineup status.",
        "processed",
        "processed",
        "manager_player_weekly_{season_id}.csv",
        producer="fantrax.api.merge_master_with_api_rosters_v2",
        consumers=("Managers", "team analytics", "manager analytics"),
        schema_name="manager_player_weekly",
        working_subdirectory="models/season_{season_id}",
        snapshot_subdirectory="processed",
    ),
    _definition(
        "manager_week_summary",
        "Manager Week Summary",
        "Manager-level scoring and result summary for each gameweek.",
        "processed",
        "processed",
        "manager_week_summary_{season_id}.csv",
        producer="fantrax.live.pipeline",
        consumers=("League Hub", "Managers", "team analytics"),
        schema_name="manager_week_summary",
        working_subdirectory="models/season_{season_id}",
        snapshot_subdirectory="processed",
    ),
    _definition(
        "manager_season_summary",
        "Manager Season Summary",
        "Season-to-date manager performance summary.",
        "processed",
        "processed",
        "manager_season_summary_{season_id}.csv",
        producer="fantrax.api.merge_master_with_api_rosters_v2",
        consumers=("team analytics", "manager analytics"),
        schema_name="manager_season_summary",
    ),
    _definition(
        "matchup_week_summary",
        "Matchup Week Summary",
        "Head-to-head matchup results and scores by gameweek.",
        "processed",
        "processed",
        "matchup_week_summary_{season_id}.csv",
        producer="fantrax.api.merge_master_with_api_rosters_v2",
        consumers=("League Hub", "Managers", "team analytics"),
        schema_name="matchup_week_summary",
    ),
    _definition(
        "lineup_quality_summary",
        "Lineup Quality Summary",
        "Manager lineup completeness and quality checks by gameweek.",
        "processed",
        "processed",
        "lineup_quality_summary_{season_id}.csv",
        producer="fantrax.api.merge_master_with_api_rosters_v2",
        consumers=("Managers", "Key Output Health"),
        schema_name="lineup_quality_summary",
    ),
    _definition(
        "league_table",
        "League Table",
        "Presentation-ready league standings.",
        "analytics",
        "analytics",
        "league_table.csv",
        producer="fantrax.analytics.team.build_league_awards_views",
        consumers=("League Hub", "Managers"),
        schema_name="league_table",
    ),
    _definition(
        "weekly_awards",
        "Weekly Awards",
        "Award winners calculated for each gameweek.",
        "analytics",
        "analytics",
        "weekly_awards.csv",
        producer="fantrax.analytics.team.build_league_awards_views",
        consumers=("League Hub", "Award Detail"),
        schema_name="weekly_awards",
    ),
    _definition(
        "award_leaderboards",
        "Award Leaderboards",
        "Season award standings and counts.",
        "analytics",
        "analytics",
        "award_leaderboards.csv",
        producer="fantrax.analytics.team.build_league_awards_views",
        consumers=("League Hub", "Award Detail"),
        schema_name="award_leaderboards",
    ),
    _definition(
        "manager_profile_summary",
        "Manager Profile Summary",
        "Consolidated manager performance and style metrics.",
        "analytics",
        "analytics",
        "manager_profile_summary.csv",
        producer="fantrax.analytics.manager.build_efficiency_ghost_awards_views",
        consumers=("League Hub", "Managers"),
        schema_name="manager_profile_summary",
    ),
    _definition(
        "manager_streaks",
        "Manager Streaks",
        "Winning, losing, and scoring streaks for managers.",
        "analytics",
        "analytics",
        "manager_streaks.csv",
        producer="fantrax.analytics.team.build_league_awards_views",
        consumers=("League Hub", "Award Detail", "Managers"),
        schema_name="manager_streaks",
    ),
    _definition(
        "lineup_changes",
        "Lineup Changes",
        "Week-over-week manager lineup changes.",
        "analytics",
        "analytics",
        "lineup_changes.csv",
        producer="fantrax.analytics.team.build_league_awards_views",
        consumers=("League Hub", "manager analytics"),
        schema_name="lineup_changes",
    ),
    _definition(
        "closest_games",
        "Closest Games",
        "Smallest winning margins across league matchups.",
        "analytics",
        "analytics",
        "closest_games.csv",
        producer="fantrax.analytics.team.build_league_awards_views",
        consumers=("League Hub", "Award Detail"),
        schema_name="matchup_extremes",
    ),
    _definition(
        "biggest_blowouts",
        "Biggest Blowouts",
        "Largest winning margins across league matchups.",
        "analytics",
        "analytics",
        "biggest_blowouts.csv",
        producer="fantrax.analytics.team.build_league_awards_views",
        consumers=("League Hub", "Award Detail"),
        schema_name="matchup_extremes",
    ),
    _definition(
        "league_hub_cards",
        "League Hub Cards",
        "Presentation-ready headline metrics for the League Hub.",
        "analytics",
        "analytics",
        "league_hub_cards.csv",
        producer="fantrax.analytics.team.build_league_awards_views",
        consumers=("League Hub",),
        schema_name="league_hub_cards",
    ),
    _definition(
        "manager_efficiency_weekly",
        "Manager Efficiency Weekly",
        "Preferred weekly lineup-efficiency view.",
        "analytics",
        "analytics",
        "manager_efficiency_weekly_v2.csv",
        producer="fantrax.analytics.manager.build_decision_views",
        consumers=("Managers",),
        aliases=("manager_efficiency_weekly_v2", "manager_efficiency_weekly_legacy"),
        schema_name="manager_efficiency_weekly",
    ),
    _definition(
        "lineup_decision_details",
        "Lineup Decision Details",
        "Preferred player-level lineup decision and optimization detail.",
        "analytics",
        "analytics",
        "lineup_decision_details_v2.csv",
        producer="fantrax.analytics.manager.build_decision_views",
        consumers=("Managers",),
        aliases=("lineup_decision_details_v2", "lineup_decision_details_legacy"),
        schema_name="lineup_decision_details",
    ),
    _definition(
        "manager_efficiency_season",
        "Manager Efficiency Season",
        "Season-level manager lineup-efficiency summary.",
        "analytics",
        "analytics",
        "manager_efficiency_season.csv",
        producer="fantrax.analytics.manager.build_efficiency_ghost_awards_views",
        consumers=("Key Output Health", "manager analytics"),
        schema_name="manager_efficiency_season",
    ),
    _definition(
        "ghost_points_player_leaders",
        "Ghost Points Player Leaders",
        "Player leaderboard for unrostered fantasy points.",
        "analytics",
        "analytics",
        "ghost_points_player_leaders.csv",
        producer="fantrax.analytics.manager.build_efficiency_ghost_awards_views",
        consumers=("Key Output Health", "manager analytics"),
        schema_name="ghost_points_player_leaders",
    ),
    _definition(
        "ghost_points_manager_weekly",
        "Ghost Points Manager Weekly",
        "Weekly manager totals for missed unrostered-player points.",
        "analytics",
        "analytics",
        "ghost_points_manager_weekly.csv",
        producer="fantrax.analytics.manager.build_efficiency_ghost_awards_views",
        consumers=("Managers", "Key Output Health"),
        schema_name="ghost_points_manager_weekly",
    ),
    _definition(
        "ghost_points_manager_season",
        "Ghost Points Manager Season",
        "Season manager totals for missed unrostered-player points.",
        "analytics",
        "analytics",
        "ghost_points_manager_season.csv",
        producer="fantrax.analytics.manager.build_efficiency_ghost_awards_views",
        consumers=("Key Output Health", "manager analytics"),
        schema_name="ghost_points_manager_season",
    ),
    _definition(
        "position_points_manager_season",
        "Position Points Manager Season",
        "Manager scoring totals by player position for the season.",
        "analytics",
        "analytics",
        "position_points_manager_season.csv",
        producer="fantrax.analytics.manager.build_efficiency_ghost_awards_views",
        consumers=("Managers", "Key Output Health"),
        schema_name="position_points_manager_season",
    ),
    _definition(
        "roster_adds_weekly",
        "Roster Adds Weekly",
        "Weekly player additions by manager.",
        "analytics",
        "analytics",
        "roster_adds_weekly.csv",
        producer="fantrax.analytics.manager.build_efficiency_ghost_awards_views",
        consumers=("Managers", "Key Output Health"),
        schema_name="roster_adds_weekly",
    ),
    _definition(
        "roster_adds_leaders",
        "Roster Adds Leaders",
        "Season leaderboard for roster additions.",
        "analytics",
        "analytics",
        "roster_adds_leaders.csv",
        producer="fantrax.analytics.manager.build_efficiency_ghost_awards_views",
        consumers=("Key Output Health", "manager analytics"),
        schema_name="roster_adds_leaders",
    ),
    _definition(
        "manager_awards_dynamic",
        "Manager Awards Dynamic",
        "Derived manager awards and supporting metrics.",
        "analytics",
        "analytics",
        "manager_awards_dynamic.csv",
        producer="fantrax.analytics.manager.build_efficiency_ghost_awards_views",
        consumers=("Key Output Health", "manager analytics"),
        schema_name="manager_awards_dynamic",
    ),
    _definition(
        "manager_behavior_weekly",
        "Manager Behavior Weekly",
        "Weekly manager behavior metrics.",
        "analytics",
        "analytics",
        "manager_behavior_weekly.csv",
        producer=None,
        consumers=("Managers", "Key Output Health"),
        required=False,
        schema_name="manager_behavior_weekly",
    ),
    _definition(
        "manager_behavior_season",
        "Manager Behavior Season",
        "Season-level manager behavior metrics.",
        "analytics",
        "analytics",
        "manager_behavior_season.csv",
        producer=None,
        consumers=("Managers", "Key Output Health"),
        required=False,
        schema_name="manager_behavior_season",
    ),
    _definition(
        "formation_weekly",
        "Formation Weekly",
        "Weekly manager formation selections and results.",
        "analytics",
        "analytics",
        "formation_weekly.csv",
        producer=None,
        consumers=("Managers", "Key Output Health"),
        required=False,
        schema_name="formation_weekly",
    ),
    _definition(
        "formation_manager_summary",
        "Formation Manager Summary",
        "Manager-level formation usage summary.",
        "analytics",
        "analytics",
        "formation_manager_summary.csv",
        producer=None,
        consumers=("Managers", "Key Output Health"),
        required=False,
        schema_name="formation_manager_summary",
    ),
    _definition(
        "formation_league_summary",
        "Formation League Summary",
        "League-level formation usage summary.",
        "analytics",
        "analytics",
        "formation_league_summary.csv",
        producer=None,
        consumers=("Key Output Health",),
        required=False,
        schema_name="formation_league_summary",
    ),
    _definition(
        "scoring_periods",
        "Fantrax Scoring Periods",
        "Mapping between Fantrax gameweeks and scoring-period dates.",
        "reference",
        "reference",
        "fantrax_scoring_periods_{season_id}.csv",
        producer=None,
        consumers=("League Hub", "master weekly builder"),
        cacheable=True,
        mutable=False,
        schema_name="scoring_periods",
    ),
    _definition(
        "api_player_bridge",
        "API Player Bridge",
        "Crosswalk from Fantrax API player IDs to canonical Fantrax player IDs.",
        "reference",
        "reference",
        "api_to_master_player_id_bridge_{season_id}.csv",
        producer="fantrax.api.build_name_based_api_player_bridge",
        consumers=("Fantrax API merge",),
        aliases=("api_to_master_player_id_bridge", "api_player_id_bridge"),
        mutable=True,
        schema_name="api_player_bridge",
    ),
    _definition(
        "understat_crosswalk",
        "Understat–Fantrax Crosswalk",
        "Curated identity map between Understat and Fantrax players.",
        "reference",
        "reference",
        "understat_fantrax_player_id_map.csv",
        producer=None,
        consumers=("master weekly builder", "API player bridge"),
        aliases=("understat_fantrax_player_id_map",),
        mutable=True,
        schema_name="understat_crosswalk",
    ),
    _definition(
        "current_fantrax_player_pool",
        "Current Fantrax Player Pool",
        "Authoritative current Fantrax identity, eligibility, and projection fields.",
        "reference",
        "reference",
        "current_fantrax_player_pool_{season_id}.csv",
        producer="current Fantrax player-pool import",
        consumers=("Draft HQ", "draft rankings builder"),
        required=False,
        schema_name=None,
        required_columns=(
            "fantrax_player_id", "fantrax_player_name", "fantrax_position",
        ),
    ),
    _definition(
        "league_teams", "Live League Teams", "Current Fantrax manager and fantasy-team identities.",
        "live_model", "season", "league_teams_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("League Hub", "Managers", "Trade Tool"), required=False, schema_name=None,
        working_subdirectory="models/season_{season_id}", required_columns=("season_id", "manager_id", "fantasy_team_id", "manager_name"),
    ),
    _definition(
        "current_rosters", "Current Live Rosters", "Latest validated player ownership and lineup state.",
        "live_model", "season", "current_rosters_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("Players", "Managers", "League Hub", "Trade Tool"), required=False, schema_name=None,
        working_subdirectory="models/season_{season_id}", required_columns=("period", "fantrax_player_id", "registry_player_id", "fantasy_team_id"),
    ),
    _definition(
        "roster_history", "Roster History", "Player-manager roster and lineup relationship by scoring period.",
        "live_model", "season", "roster_history_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("Players", "Managers", "Trade Tool"), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
    ),
    _definition(
        "roster_change_events", "Roster Change Events", "Append-only deterministic changes between distinct roster snapshots.",
        "live_model", "season", "roster_change_events_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("Players", "Managers", "League Hub"), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
    ),
    _definition(
        "roster_snapshots_manifest", "Roster Snapshots Manifest", "Latest immutable roster snapshot checksum and chain status.",
        "live_model", "season", "roster_snapshots_manifest_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("Update Pipeline",), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
    ),
    _definition(
        "roster_tracking_quality", "Roster Tracking Quality", "Roster, event, ownership, history, and checksum-chain validation.",
        "live_model", "season", "roster_tracking_quality_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("Update Pipeline", "Key Output Health"), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
    ),
    _definition(
        "league_standings", "Live League Standings", "Authoritative Fantrax table and scoring totals.",
        "live_model", "season", "league_standings_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("League Hub", "Managers"), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
    ),
    _definition(
        "weekly_matchups", "Weekly Matchups", "Fantrax head-to-head schedule, scores, winners, and margins.",
        "live_model", "season", "weekly_matchups_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("League Hub", "Managers"), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
    ),
    _definition(
        "fantrax_matchups", "Authoritative Fantrax Matchups", "Validated private live-scoring manager totals and results.",
        "live_model", "season", "fantrax_matchups_{season_id}.csv", producer="fantrax.live.matchup_acquisition",
        consumers=("League Hub", "Managers", "Update Pipeline"), required=False, schema_name=None,
        working_subdirectory="models/season_{season_id}", required_columns=("period","matchup_id","home_team_id","away_team_id","home_score","away_score"),
    ),
    _definition(
        "fantrax_live_player_scoring", "Fantrax Live Player Scoring", "Private live-scoring FPts and lineup state used to reconcile official manager totals.",
        "live_model", "season", "fantrax_live_player_scoring_{season_id}.csv", producer="fantrax.live.matchup_acquisition",
        consumers=("Managers", "Update Pipeline", "quality reporting"), required=False, schema_name=None,
        working_subdirectory="models/season_{season_id}", required_columns=("period","fantrax_team_id","fantrax_player_id","lineup_status","live_scoring_fpts"),
    ),
    _definition(
        "manager_week_start_sit_summary", "Manager Week Start Sit Summary", "Finalized canonical XI outcomes explained using the existing Efficiency optimum.",
        "live_model", "season", "manager_week_start_sit_summary_{season_id}.csv", producer="fantrax.live.start_sit",
        consumers=("Managers",), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
        required_columns=("manager_id", "gameweek"),
    ),
    _definition(
        "manager_week_start_sit_decisions", "Manager Week Start Sit Decisions", "Finalized canonical XI outcomes explained using the existing Efficiency optimum.",
        "live_model", "season", "manager_week_start_sit_decisions_{season_id}.csv", producer="fantrax.live.start_sit",
        consumers=("Managers",), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
        required_columns=("manager_id", "gameweek"),
    ),
    _definition(
        "manager_week_decision_summary", "Manager Week Decision Summary", "Canonical final lineup counts and descriptive event activity; no decision grading.",
        "live_model", "season", "manager_week_decision_summary_{season_id}.csv", producer="fantrax.live.manager_decisions",
        consumers=("Managers",), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
        required_columns=("manager_id", "gameweek", "lineup_event_count", "event_coverage_status"),
    ),
    _definition(
        "manager_event_timeline", "Manager Event Timeline", "Chronological individual transaction and lineup actions with candidate group identifiers.",
        "live_model", "season", "manager_event_timeline_{season_id}.csv", producer="fantrax.live.manager_decisions",
        consumers=("Managers",), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
        required_columns=("manager_id", "gameweek", "source_event_id", "event_timestamp"),
    ),
    _definition(
        "transaction_events", "Transaction Events", "Official CSV claim, drop and lineup-change event observations; separate from current ownership.",
        "live_model", "season", "transaction_events_{season_id}.csv", producer="fantrax.live.event_imports",
        consumers=(), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
        required_columns=("transaction_event_id", "transaction_group_id", "raw_transaction_type", "player_id", "manager_id", "event_timestamp"),
    ),
    _definition(
        "lineup_events", "Lineup Events", "Official CSV lineup transitions with raw state and slot observations.",
        "live_model", "season", "lineup_events_{season_id}.csv", producer="fantrax.live.event_imports",
        consumers=(), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
        required_columns=("lineup_event_id", "raw_from", "raw_to", "player_id", "manager_id", "event_timestamp"),
    ),
    _definition(
        "league_transactions", "League Transactions", "Normalized draft, add, drop, waiver, trade, and commissioner events.",
        "live_model", "season", "league_transactions_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("Players", "Managers", "Trade Tool"), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
    ),
    _definition(
        "player_ownership", "Current Player Ownership", "One current ownership or availability state per Fantrax player.",
        "live_model", "season", "player_ownership_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("Players", "Draft HQ", "Trade Tool"), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
    ),
    _definition(
        "current_player_weekly", "Current Player Weekly", "Authoritative player-period facts from proven cached weekly sources.",
        "live_model", "season", "current_player_weekly_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("Players", "Managers", "Weekly Reports"), required=False, schema_name=None,
        working_subdirectory="models/season_{season_id}", required_columns=("season_id","period","fantrax_player_id","fantasy_points"),
    ),
    _definition(
        "player_match_participation", "Player Match Participation", "Canonical current player-match appearances, starts, minutes, roles, and clean-sheet context.",
        "live_model", "season", "player_match_participation_{season_id}.csv", producer="scripts.build_current_player_participation",
        consumers=("Players", "Comparison", "quality reporting"), required=False, schema_name=None,
        working_subdirectory="models/season_{season_id}", required_columns=("canonical_match_id","canonical_player_id","appeared","started","minutes"),
    ),
    _definition(
        "current_player_season_summary", "Current Player Season Summary", "Canonical current player totals and shared rate bases.",
        "live_model", "season", "current_player_season_summary_{season_id}.csv", producer="scripts.build_current_player_participation",
        consumers=("Players", "Comparison"), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
    ),
    _definition(
        "current_player_match_log", "Current Player Match Log", "One row per observed current player-match with fantasy and provider facts.",
        "live_model", "season", "current_player_match_log_{season_id}.csv", producer="scripts.build_current_player_participation",
        consumers=("Players", "Match Analysis"), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
    ),
    _definition(
        "league_active_player_weekly", "League Active Player Weekly", "Historically attributed active fantasy starters used by League Hub awards.",
        "live_model", "season", "league_active_player_weekly_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("League Hub","Managers"), required=False, schema_name=None,
        working_subdirectory="models/season_{season_id}", required_columns=("season_id","period","manager_id","fantrax_player_id","active_start","fantrax_points"),
    ),
    _definition(
        "live_player_weekly_enriched", "Unified Live Player Weekly", "Fantrax-authoritative current player-week enriched with approved WhoScored and optional Understat fields.",
        "live_model", "season", "live_player_weekly_enriched_{season_id}.csv", producer="scripts.build_live_weekly_unified",
        consumers=("Players", "Teams", "Fantasy Allowed"), required=False, schema_name=None,
        working_subdirectory="models/season_{season_id}", required_columns=("period","fantrax_player_id","fantasy_points"),
    ),
    _definition(
        "understat_player_weekly", "Understat Player Weekly", "Supplemental match facts mapped to authoritative Fantrax scoring periods.",
        "live_model", "season", "understat_player_weekly_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("Players", "Available Players", "quality reporting"), required=False, schema_name=None,
        working_subdirectory="models/season_{season_id}", required_columns=("season_id","period","fantrax_player_id","understat_player_id"),
    ),
    _definition(
        "understat_player_match", "Understat Player Match", "Current-season provider xG/xA facts with exact match and player identity status.",
        "live_model", "season", "understat_player_match_{season_id}.csv", producer="scripts.build_understat_live_products",
        consumers=("Players", "quality reporting"), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
        required_columns=("canonical_match_id","understat_match_id","understat_player_id","xg","xa","identity_status"),
    ),
    _definition(
        "understat_team_match", "Understat Team Match", "Current-season team xG/xGA perspectives with reciprocal opponent facts.",
        "live_model", "season", "understat_team_match_{season_id}.csv", producer="scripts.build_understat_live_products",
        consumers=("Teams", "quality reporting"), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
        required_columns=("canonical_match_id","canonical_club_id","opponent_id","xg","xga"),
    ),
    _definition(
        "team_position_fantasy_allowed_current", "Current Team Position Fantasy Allowed", "Current Fantrax match-attributable production allowed by opponent and position.",
        "live_model", "season", "team_position_fantasy_allowed_current_{season_id}.csv", producer="scripts.build_live_weekly_unified",
        consumers=("Teams",), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
        required_columns=("opponent_id","position_group","matches","points_allowed_per_match"),
    ),
    _definition(
        "fantrax_stat_dictionary", "Fantrax Stat Dictionary", "League scoring definitions and normalized live-stat source classifications.",
        "reference", "reference", "fantrax_stat_dictionary_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("Players", "Operations Center", "documentation"), required=False, schema_name=None,
        required_columns=("fantrax_stat_id","raw_label","normalized_field","source_class"),
    ),
    _definition(
        "live_player_analytics", "Live Player Analytics", "Canonical presentation-ready live player, ownership, draft, and historical context.",
        "live_model", "season", "live_player_analytics_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("Players", "Managers", "League Hub"), required=False, schema_name=None,
        working_subdirectory="models/season_{season_id}", required_columns=("season_id", "fantrax_player_id", "player_name", "available"),
    ),
    _definition(
        "live_manager_analytics", "Live Manager Analytics", "Centralized current-roster and draft-retention manager metrics.",
        "live_model", "season", "live_manager_analytics_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("Managers", "League Hub"), required=False, schema_name=None,
        working_subdirectory="models/season_{season_id}", required_columns=("season_id", "manager_id", "roster_count"),
    ),
    _definition(
        "live_position_strength", "Live Position Strength", "League-relative manager position groups using one canonical assignment per player.",
        "live_model", "season", "live_position_strength_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("Managers", "League Hub"), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
    ),
    _definition(
        "live_league_summary", "Live League Summary", "Cached League Hub manager summaries, movement, form, scoring and roster context.",
        "live_model", "season", "live_league_summary_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("League Hub",), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
        required_columns=("season_id", "manager_id", "current_rank", "movement"),
    ),
    _definition(
        "available_players", "Available Players", "Free agents from the canonical live player frame.",
        "live_model", "season", "available_players_{season_id}.csv", producer="fantrax.live.pipeline",
        consumers=("Players", "League Hub"), required=False, schema_name=None,
        working_subdirectory="models/season_{season_id}", required_columns=("fantrax_player_id", "available"),
    ),
    _definition(
        "cup_configuration", "Cup Configuration", "Season-specific Cup format, schedule, scoring, and tiebreak rules.",
        "reference", "season", "cup_configuration_{season_id}.csv", producer="league administration",
        consumers=("Cup Tournament", "Operations Center"), required=False, schema_name=None,
        working_subdirectory="reference", required_columns=("season","tournament_name","teams","byes","seeding_week"),
    ),
    _definition(
        "cup_seed_snapshot", "Cup Seed Snapshot", "Immutable manager seeds frozen at the configured seeding week.",
        "cup", "season", "cup_seed_snapshot_{season_id}.csv", producer="scripts.manage_cup",
        consumers=("Cup Tournament",), required=False, mutable=False, schema_name=None, working_subdirectory="models/season_{season_id}",
        required_columns=("manager_id","seed","league_rank","snapshot_week","snapshot_timestamp"),
    ),
    *(
        _definition(key, label, description, "cup", "season", f"{key}_{{season_id}}.csv", producer="scripts.manage_cup",
            consumers=("Cup Tournament","Managers","League Hub"), required=False, schema_name=None, working_subdirectory="models/season_{season_id}")
        for key,label,description in (
            ("cup_schedule","Cup Schedule","Configured tournament stages and gameweeks."),
            ("cup_matchups","Cup Matchups","Current bracket matchups, scores, states, and progression paths."),
            ("cup_results","Cup Results","Finalized Cup matchup results."),
            ("cup_records","Cup Records","Manager Cup records and deepest runs."),
        )
    ),
    _definition(
        "live_season_manifest", "Live Season Manifest", "Checksums, provenance, coverage, and validation state for live datasets.",
        "manifest", "season", "live_season_manifest_{season_id}.json", producer="fantrax.live.pipeline",
        consumers=("Update Pipeline", "Key Output Health"), required=False, schema_name=None, working_subdirectory="models/season_{season_id}",
    ),
    _definition(
        "draft_rankings",
        "Draft Rankings",
        "Ranked preseason player recommendations for the target draft season.",
        "model",
        "draft",
        "draft_rankings_{season_id}.csv",
        producer="analytics.draft.builder",
        consumers=("Draft HQ",),
        schema_name="draft_rankings",
    ),
    _definition(
        "draft_results", "Completed Draft Results", "Completed draft joined to frozen draft-day analytics.",
        "model", "draft", "draft_results_graded_input_{season_id}.csv",
        producer="analytics.draft.grading", consumers=("Draft HQ", "draft grade reports"),
        required=False, schema_name=None, required_columns=("overall_pick", "manager", "player", "draft_score"),
    ),
    _definition(
        "draft_day_rankings_snapshot", "Draft-Day Rankings Snapshot", "Immutable rankings used for completed-draft grading.",
        "snapshot", "draft", "draft_rankings_draft_day_{season_id}.csv",
        producer="scripts.build_draft_grades", consumers=("draft grading",), required=False,
        mutable=False, cacheable=True, schema_name=None,
        working_subdirectory="snapshots/draft_{season_id}", snapshot_subdirectory="snapshots/draft_{season_id}",
    ),
    _definition(
        "draft_pick_grades", "Draft Pick Grades", "Deterministic grade and labels for every completed selection.",
        "model", "draft", "draft_pick_grades_{season_id}.csv", producer="analytics.draft.grading",
        consumers=("Draft HQ", "draft grade reports"), required=False, schema_name=None,
        required_columns=("overall_pick", "manager", "player", "pick_grade"),
    ),
    _definition(
        "draft_manager_grades", "Draft Manager Grades", "Reconciled manager-level completed-draft grades.",
        "model", "draft", "draft_manager_grades_{season_id}.csv", producer="analytics.draft.grading",
        consumers=("Draft HQ", "draft grade reports"), required=False, schema_name=None,
        required_columns=("overall_rank", "manager", "overall_score", "overall_grade"),
    ),
    _definition(
        "draft_category_scores", "Draft Category Scores", "Long-form manager draft-grade category contributions.",
        "model", "draft", "draft_category_scores_{season_id}.csv", producer="analytics.draft.grading",
        consumers=("Draft HQ", "draft grade reports"), required=False, schema_name=None,
    ),
    _definition(
        "draft_position_grades", "Draft Position Grades", "Fantasy-facing manager position-group metrics and grades.",
        "model", "draft", "draft_position_grades_{season_id}.csv", producer="analytics.draft.grading",
        consumers=("Draft HQ", "draft grade reports"), required=False, schema_name=None,
    ),
    _definition(
        "draft_awards", "Draft Awards", "Deterministic completed-draft league awards.",
        "model", "draft", "draft_awards_{season_id}.csv", producer="analytics.draft.grading",
        consumers=("Draft HQ", "draft grade reports"), required=False, schema_name=None,
    ),
    _definition(
        "draft_match_report", "Draft Player Match Report", "Auditable draft-result to frozen-player identity matches.",
        "quality", "draft", "draft_player_match_report.csv", producer="analytics.draft.grading",
        consumers=("Draft HQ", "Identity Review"), required=False, schema_name=None,
        working_subdirectory="quality/draft_results_{season_id}", snapshot_subdirectory="quality/draft_results_{season_id}",
    ),
    _definition(
        "draft_player_pool",
        "Draft Player Pool",
        "Enriched player pool used to calculate draft rankings.",
        "model",
        "draft",
        "draft_player_pool_{season_id}.csv",
        producer="analytics.draft.builder",
        consumers=("Draft HQ", "draft rankings builder"),
        schema_name="draft_player_pool",
    ),
    _definition(
        "draft_eligibility_overrides",
        "Draft Eligibility Overrides",
        "Optional curated overrides for current-season draft eligibility.",
        "reference",
        "reference",
        "draft_eligibility_overrides_{season_id}.csv",
        producer=None,
        consumers=("Draft HQ", "draft rankings builder"),
        required=False,
        schema_name="draft_eligibility_overrides",
        working_subdirectory="imports/draft",
        snapshot_subdirectory="imports/draft",
    ),
    _definition(
        "current_squad_snapshot",
        "Current Squad Snapshot",
        "Cached provider-neutral current Premier League player population.",
        "reference",
        "reference",
        "fpl_players_{season_id}.csv",
        producer="analytics.current_squads.builder",
        consumers=("player registry builder",),
        schema_name="current_squad_snapshot",
        working_subdirectory="reference/current_squads",
        snapshot_subdirectory="reference/current_squads",
        required_columns=(
            "provider_player_id", "player_name", "team_code", "position",
            "active_epl", "provider", "retrieved_at", "season_id",
        ),
    ),
    _definition(
        "player_registry",
        "Player Registry",
        "Canonical season-aware player identity and current-club registry.",
        "reference",
        "reference",
        "player_registry_{season_id}.csv",
        producer="analytics.player_registry.builder",
        consumers=(
            "Draft HQ", "League Hub", "Awards", "player analytics",
        ),
        schema_name="player_registry",
        required_columns=(
            "registry_player_id", "canonical_name", "registry_status",
            "match_method", "identity_confidence", "season_id",
        ),
    ),
    _definition(
        "player_registry_quality",
        "Player Registry Quality Report",
        "Aggregate validation and coverage metrics for the Player Registry.",
        "quality",
        "reference",
        "player_registry_quality_report.csv",
        producer="analytics.player_registry.builder",
        consumers=("registry validation",),
        required=False,
        schema_name="player_registry_quality",
        working_subdirectory="quality/player_registry_{season_id}",
        snapshot_subdirectory="quality/player_registry_{season_id}",
        required_columns=("metric", "value"),
    ),
    _definition(
        "player_registry_unresolved",
        "Player Registry Unresolved",
        "Unresolved and ambiguous player identity diagnostics.",
        "quality",
        "reference",
        "player_registry_unresolved.csv",
        producer="analytics.player_registry.builder",
        consumers=("registry validation",),
        required=False,
        schema_name="player_registry",
        working_subdirectory="quality/player_registry_{season_id}",
        snapshot_subdirectory="quality/player_registry_{season_id}",
    ),
    _definition(
        "player_identity_review",
        "Player Identity Review",
        "Ranked, non-binding current-player candidates for unresolved identities.",
        "reference",
        "reference",
        "player_identity_review_{season_id}.csv",
        producer="analytics.player_registry.review",
        consumers=("Identity Review",),
        required=False,
        schema_name="player_identity_review",
        working_subdirectory="reference/player_registry",
        snapshot_subdirectory="reference/player_registry",
        required_columns=(
            "season_id", "registry_player_id", "fantrax_player_id",
            "historical_name", "current_candidate_fpl_id",
            "current_candidate_name", "candidate_score", "confidence_class",
            "candidate_unique", "review_status",
        ),
    ),
    _definition(
        "player_alias_overrides",
        "Player Alias Review Decisions",
        "Audited pair-specific approvals and ignored identity suggestions.",
        "reference",
        "reference",
        "player_alias_overrides_{season_id}.csv",
        producer="Identity Review",
        consumers=("Identity Review", "player registry builder"),
        required=False,
        schema_name="player_alias_overrides",
        working_subdirectory="reference/player_registry",
        snapshot_subdirectory="reference/player_registry",
        required_columns=(
            "season_id", "historical_name", "historical_fantrax_player_id",
            "current_fpl_name", "current_fpl_player_id", "decision",
            "review_note", "reviewed_at", "source",
        ),
    ),
    _definition(
        "season_manifest",
        "Season Manifest",
        "Immutable inventory and checksums for a finalized season snapshot.",
        "manifest",
        "reports",
        "season_manifest.json",
        producer="fantrax.finalize.finalize_fantrax_season_2526",
        consumers=("Update Pipeline", "snapshot validation"),
        aliases=("finalization_manifest",),
        cacheable=False,
        mutable=False,
        schema_name="season_manifest",
        working_subdirectory="seasons/{season_id}",
        snapshot_subdirectory="",
    ),
    _definition(
        "finalization_validation_report",
        "Finalization Validation Report",
        "Validation summary generated when a season snapshot is finalized.",
        "report",
        "reports",
        "finalization_validation_report.txt",
        producer="fantrax.finalize.finalize_fantrax_season_2526",
        consumers=("Reports", "Update Pipeline"),
        required=False,
        cacheable=False,
        mutable=False,
        working_subdirectory="seasons/{season_id}/reports",
        snapshot_subdirectory="reports",
    ),
    _definition(
        "api_merge_report",
        "API Merge Validation Report",
        "Human-readable validation report for the Fantrax API roster merge.",
        "report",
        "reports",
        "api_merge_validation_report_{season_id}.txt",
        producer="fantrax.api.merge_master_with_api_rosters_v2",
        consumers=("Reports", "Key Output Health"),
        aliases=("api_merge_validation_report",),
        cacheable=False,
        mutable=True,
        working_subdirectory="processed",
        snapshot_subdirectory="processed",
    ),
    _definition(
        "league_awards_report",
        "League Awards Report",
        "Validation and output summary for league awards analytics.",
        "report",
        "reports",
        "league_awards_report.txt",
        producer="fantrax.analytics.team.build_league_awards_views",
        consumers=("Reports",),
        required=False,
        cacheable=False,
        working_subdirectory="seasons/{season_id}/analytics_views",
        snapshot_subdirectory="analytics_views",
    ),
    _definition(
        "efficiency_ghost_awards_report",
        "Efficiency and Ghost Awards Report",
        "Validation summary for efficiency, ghost-points, and manager awards.",
        "report",
        "reports",
        "efficiency_ghost_awards_report.txt",
        producer="fantrax.analytics.manager.build_efficiency_ghost_awards_views",
        consumers=("Reports",),
        required=False,
        cacheable=False,
        working_subdirectory="seasons/{season_id}/analytics_views",
        snapshot_subdirectory="analytics_views",
    ),
    _definition(
        "formation_report",
        "Formation Report",
        "Validation summary for formation analytics.",
        "report",
        "reports",
        "formation_report.txt",
        producer=None,
        consumers=("Reports",),
        required=False,
        cacheable=False,
        working_subdirectory="seasons/{season_id}/analytics_views",
        snapshot_subdirectory="analytics_views",
    ),
    _definition(
        "recent_season_reports",
        "Recent Season Reports",
        "Text reports stored directly in a season reports directory.",
        "report",
        "reports",
        "*.txt",
        producer=None,
        consumers=("Reports",),
        required=False,
        cacheable=False,
        working_subdirectory="seasons/{season_id}/reports",
        snapshot_subdirectory="reports",
        family=True,
    ),
)


class DatasetRegistry:
    """Store and query validated logical dataset definitions."""

    def __init__(
        self,
        definitions: Iterable[DatasetDefinition] | None = None,
    ) -> None:
        supplied = CORE_DATASETS if definitions is None else tuple(definitions)
        self._definitions = tuple(supplied)
        self._by_key: dict[str, DatasetDefinition] = {}
        self._aliases: dict[str, str] = {}
        self.validate()

    def validate(self) -> None:
        """Validate all definitions and rebuild lookup indexes.

        Raises:
            RegistryValidationError: if a key, alias, or definition is invalid.
        """

        by_key: dict[str, DatasetDefinition] = {}
        aliases: dict[str, str] = {}

        for definition in self._definitions:
            self._validate_definition(definition)

            if definition.key in by_key:
                raise RegistryValidationError(
                    f"Duplicate dataset key: {definition.key!r}"
                )
            by_key[definition.key] = definition

        for definition in self._definitions:
            for alias in definition.aliases:
                if alias in by_key:
                    raise RegistryValidationError(
                        f"Alias {alias!r} conflicts with a dataset key"
                    )
                if alias in aliases:
                    raise RegistryValidationError(
                        f"Duplicate dataset alias: {alias!r}"
                    )
                aliases[alias] = definition.key

        self._by_key = by_key
        self._aliases = aliases

    def get(self, key: str) -> DatasetDefinition:
        """Return a definition by canonical key or alias.

        Raises:
            KeyError: if neither the key nor alias is registered.
        """

        canonical_key = self.resolve_alias(key)
        try:
            return self._by_key[canonical_key]
        except KeyError as exc:
            raise KeyError(f"Unknown dataset key or alias: {key!r}") from exc

    def list_all(self) -> tuple[DatasetDefinition, ...]:
        """Return every definition in deterministic registration order."""

        return self._definitions

    def find_by_classification(
        self,
        classification: str,
    ) -> tuple[DatasetDefinition, ...]:
        """Return definitions with the requested classification."""

        return tuple(
            definition
            for definition in self._definitions
            if definition.classification == classification
        )

    def find_by_namespace(
        self,
        namespace: str,
    ) -> tuple[DatasetDefinition, ...]:
        """Return definitions in the requested logical namespace."""

        return tuple(
            definition
            for definition in self._definitions
            if definition.namespace == namespace
        )

    def resolve_alias(self, key: str) -> str:
        """Return the canonical key for a key or alias.

        Unknown values are returned unchanged so callers can resolve first and
        decide separately whether lookup is required.
        """

        return self._aliases.get(key, key)

    def describe(self, key: str) -> str:
        """Return a concise human-readable description of a dataset."""

        definition = self.get(key)
        requirement = "required" if definition.required else "optional"
        return (
            f"{definition.display_name} ({definition.key}) — "
            f"{definition.description} "
            f"[{definition.classification}/{definition.namespace}; "
            f"{requirement}; {definition.filename_template}]"
        )

    @staticmethod
    def _validate_definition(definition: DatasetDefinition) -> None:
        if not isinstance(definition, DatasetDefinition):
            raise RegistryValidationError(
                "Registry entries must be DatasetDefinition instances"
            )

        required_text = {
            "key": definition.key,
            "display_name": definition.display_name,
            "description": definition.description,
            "classification": definition.classification,
            "namespace": definition.namespace,
            "filename_template": definition.filename_template,
        }
        for field_name, value in required_text.items():
            if not isinstance(value, str) or not value.strip():
                raise RegistryValidationError(
                    f"{definition.key!r}: {field_name} must be non-empty text"
                )

        if not _KEY_PATTERN.fullmatch(definition.key):
            raise RegistryValidationError(
                f"Invalid dataset key {definition.key!r}; use lowercase snake_case"
            )

        if "/" in definition.filename_template or "\\" in definition.filename_template:
            raise RegistryValidationError(
                f"{definition.key!r}: filename_template must not include a path"
            )

        if (
            any(character in definition.filename_template for character in "*?[")
            and not definition.family
        ):
            raise RegistryValidationError(
                f"{definition.key!r}: wildcard filename templates require family=True"
            )

        for field_name, value in (
            ("working_subdirectory", definition.working_subdirectory),
            ("snapshot_subdirectory", definition.snapshot_subdirectory),
        ):
            if not isinstance(value, str):
                raise RegistryValidationError(
                    f"{definition.key!r}: {field_name} must be text"
                )
            path_parts = value.replace("\\", "/").split("/")
            if value.startswith(("/", "\\")) or ".." in path_parts:
                raise RegistryValidationError(
                    f"{definition.key!r}: {field_name} must be a safe relative path"
                )

        if len(set(definition.aliases)) != len(definition.aliases):
            raise RegistryValidationError(
                f"{definition.key!r}: aliases must be unique"
            )

        for alias in definition.aliases:
            if not _KEY_PATTERN.fullmatch(alias):
                raise RegistryValidationError(
                    f"{definition.key!r}: invalid alias {alias!r}"
                )
            if alias == definition.key:
                raise RegistryValidationError(
                    f"{definition.key!r}: alias duplicates its canonical key"
                )

        if len(set(definition.required_columns)) != len(
            definition.required_columns
        ):
            raise RegistryValidationError(
                f"{definition.key!r}: required_columns must be unique"
            )
        if any(
            not isinstance(column, str) or not column.strip()
            for column in definition.required_columns
        ):
            raise RegistryValidationError(
                f"{definition.key!r}: required_columns must contain non-empty text"
            )
