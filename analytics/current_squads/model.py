"""Current-squad schema and validation errors."""

CURRENT_SQUAD_COLUMNS = (
    "provider_player_id",
    "player_name",
    "first_name",
    "last_name",
    "team_name",
    "team_code",
    "position",
    "active_epl",
    "availability_status",
    "injury_news",
    "provider",
    "retrieved_at",
    "season_id",
)


class CurrentSquadError(RuntimeError):
    """Base current-squad service error."""


class CurrentSquadSchemaError(CurrentSquadError):
    """Provider payload does not match the expected schema."""
