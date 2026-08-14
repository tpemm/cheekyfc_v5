"""Cheeky FC Cup bracket and tournament status page."""
from __future__ import annotations
from typing import Any
import html
import pandas as pd
import streamlit as st
from components.presentation import SHARED_COMPONENT_CSS, empty_state, metric_card, page_header, section_header, status_badge
from core.services.data_manager import DataManager
from core.services.season_manager import SeasonManager
from views.live_league_hub import _load
from analytics.cup.engine import tournament_schedule

KEYS=("cup_configuration","cup_seed_snapshot","cup_schedule","cup_matchups","cup_results","cup_records")

def _card(row):
    def side(prefix):
        score=row.get(f"{prefix}_score"); score_text="Upcoming" if pd.isna(score) else f"{float(score):.1f}"
        winner=str(row.get("winner_manager_id",""))==str(row.get(f"{prefix}_manager_id","")) and bool(str(row.get("winner_manager_id","")))
        return f'<div class="cup-side {"cup-winner" if winner else ""}"><b>#{int(row[f"{prefix}_seed"])} {html.escape(str(row[f"{prefix}_manager"]))}</b><span>{score_text}</span></div>'
    return f'<div class="cup-match"><div class="cup-match-meta">GW{int(row["week"])} · {status_badge(str(row["status"]),tone="positive" if row["status"]=="Final" else "warning")}</div>{side("home")}{side("away")}</div>'

CSS="""<style>.cup-bracket{display:grid;grid-template-columns:repeat(4,minmax(220px,1fr));gap:1rem;overflow-x:auto}.cup-round{min-width:220px}.cup-round-title{font-weight:800;margin-bottom:.6rem}.cup-match{background:var(--ft-card-background);border:1px solid var(--ft-border);border-radius:var(--ft-card-radius);padding:.7rem;margin-bottom:.75rem;position:relative}.cup-match-meta{font-size:.68rem;color:var(--ft-text-muted);margin-bottom:.4rem}.cup-side{display:flex;justify-content:space-between;padding:.45rem;border-radius:6px}.cup-winner{background:#e8f3ee;color:var(--ft-positive)}@media(max-width:900px){.cup-bracket{grid-template-columns:repeat(4,240px)}}</style>"""

def render(season_id:str,*,data_manager:DataManager|None=None,season_manager:SeasonManager|None=None,ui:Any=st)->None:
    seasons=season_manager or SeasonManager(); data=data_manager or DataManager(season_manager=seasons); namespace=seasons.resolve_namespace(season_id)
    ui.markdown(SHARED_COMPONENT_CSS+CSS,unsafe_allow_html=True); frames={key:_load(data,key,season_id,namespace,ui) for key in KEYS}; config=frames["cup_configuration"]
    if config.empty: page_header(ui,"Cheeky FC Cup","A configurable knockout competition layered over official manager scores.",eyebrow="Cup Tournament",badge="Configuration missing"); empty_state(ui,"Cup configuration is unavailable","No tournament schedule can be shown safely.",action="Open Operations Center and validate Cup configuration."); return
    cfg=config.iloc[0]; matchups=frames["cup_matchups"]; final=matchups[matchups.get("status",pd.Series(index=matchups.index,dtype=object)).eq("Final")] if not matchups.empty else matchups
    champion="—"; championship=final[final.get("round",pd.Series(index=final.index,dtype=object)).eq("Championship")] if not final.empty else final
    if not championship.empty: champion=championship.iloc[-1].get("winner_manager_id","—")
    current="Preseason" if matchups.empty else next((stage for stage in ("Championship","Semifinals","Quarterfinals","Opening Round") if not matchups[matchups["round"].eq(stage)].empty and not matchups[matchups["round"].eq(stage)]["status"].eq("Final").all()),"Complete")
    schedule=frames["cup_schedule"] if not frames["cup_schedule"].empty else tournament_schedule(cfg.to_dict()); weeks=pd.to_numeric(schedule["week"],errors="coerce").dropna(); next_week=weeks.min() if not weeks.empty else int(cfg["opening_round_week"])
    page_header(ui,str(cfg["tournament_name"]),"A season-long knockout overlay using official manager fantasy scores.",eyebrow="Cup Tournament",badge=f"{current} · Next GW{int(next_week)}")
    cards=ui.columns(4)
    for column,item in zip(cards,(("Current Stage",current,"Tournament progress"),("Next Cup Week",f"GW{int(next_week)}","Configured schedule"),("Defending Champion","—","Cup history begins this season"),("Champion",champion,"Awarded after championship"))):
        with column: metric_card(ui,*item)
    if frames["cup_seed_snapshot"].empty:
        empty_state(ui,f"Tournament begins after Gameweek {int(cfg['seeding_week'])}",f"The top {int(cfg['byes'])} managers after GW{int(cfg['seeding_week'])} receive byes. The bracket remains unavailable until seeds are frozen.",action="Initialize Cup in Operations Center after the seeding week is final.")
    else:
        section_header(ui,"Bracket","Reseeding pairs the highest remaining seed with the lowest remaining seed.")
        blocks=[]
        for round_name in ("Opening Round","Quarterfinals","Semifinals","Championship"):
            rows=matchups[matchups["round"].eq(round_name)] if not matchups.empty else pd.DataFrame(); blocks.append(f'<div class="cup-round"><div class="cup-round-title">{round_name}</div>{"".join(_card(row) for _,row in rows.iterrows()) or "<div class=ft-detail>Awaiting prior round</div>"}</div>')
        ui.markdown(f'<div class="cup-bracket">{"".join(blocks)}</div>',unsafe_allow_html=True)
    section_header(ui,"Tournament Schedule","All gameweeks come from the registered season configuration."); ui.dataframe(schedule,hide_index=True,use_container_width=True)
    section_header(ui,"Rules","Official manager fantasy score decides each matchup; tied scores advance the higher seed."); ui.write(f"{int(cfg['teams'])} teams · {int(cfg['byes'])} byes · reseeding {'enabled' if bool(cfg['reseed_after_round']) else 'disabled'} · no separate Cup lineup.")
    section_header(ui,"Current Seeds","Frozen permanently once initialized."); ui.dataframe(frames["cup_seed_snapshot"],hide_index=True,use_container_width=True)
    section_header(ui,"Previous Results","Finalized Cup matchups."); ui.dataframe(frames["cup_results"],hide_index=True,use_container_width=True)
    section_header(ui,"Cup Records","Future season archive and manager Cup history."); ui.dataframe(frames["cup_records"],hide_index=True,use_container_width=True)
