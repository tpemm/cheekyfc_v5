"""Central season-aware page registry."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class PageDefinition:
    title:str; icon:str; seasons:tuple[str,...]; requires_season_data:bool=True; description:str=""

PAGE_REGISTRY:tuple[PageDefinition,...]=(
    PageDefinition("League Hub","League",("2627",),False,"Standings and season overview."),
    PageDefinition("2025/26 Season Archive","Archive",("2526",),False,"Frozen finalized historical season."),
    PageDefinition("Players","Players",("2526","2627"),False,"Historical or live player database."),
    PageDefinition("Managers","Managers",("2526","2627"),False,"Manager performance and decisions."),
    PageDefinition("Cup Tournament","Cup",("2627",),False,"Cheeky FC Cup bracket and schedule."),
    PageDefinition("Trades","Trades",("2627",),False,"Trade analysis workspace."),
    PageDefinition("Weekly Reports","Weekly",("2627",),False,"Weekly league reports."),
    PageDefinition("History","History",("2526","2627"),False,"Historical league archive."),
    PageDefinition("Draft HQ","Draft",("2627",),False,"Preseason rankings and live-draft workspace."),
    PageDefinition("Award Detail","Awards",("2526",),True,"Season and weekly awards."),
    PageDefinition("Identity Review","ID",("2627",),False,"Review unresolved player identities."),
    PageDefinition("Operations Center","Operations",("2526","2627"),False,"League operations."),
    PageDefinition("Raw Data Browser","Data",("2526","2627","all_time"),False,"Inspect project data files."),
    PageDefinition("Key Output Health","Health",("2526","2627","all_time"),False,"Validate required outputs."),
    PageDefinition("Reports","Reports",("2526","2627","all_time"),False,"Review logs and reports."),
)
def pages_for_season(season_id): return [page for page in PAGE_REGISTRY if season_id in page.seasons]
def get_page(title): return next((page for page in PAGE_REGISTRY if page.title==title),None)
