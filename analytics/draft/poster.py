"""Deterministic Pillow poster generation for completed draft grades."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from analytics.draft.grading import best_legal_xi
from analytics.draft.presentation import normalize_fantrax_positions
from analytics.draft.share import build_share_summary


POSTER_SIZE = (2400, 3200)
RADAR_AXES = ("Projected XI", "Draft Value", "Fantasy / 90", "Ghost / 90", "xGI / 90", "Starting XI Minutes")
RADAR_FIELDS = ("projected_starting_xi_points", "draft_value", "fantasy_points_per_90", "ghost_points_per_90", "xgi_per_90", "starting_xi_minutes_pct")
MIN_XI_MINUTES_COVERAGE = 8
POSITION_WEIGHTS = {
    "Defense + GK": {"projected_points": .45, "fantasy_per_90": .20, "ghost_per_90": .15, "projected_minutes": .15, "data_confidence": .05},
    "Midfield": {"projected_points": .40, "fantasy_per_90": .20, "ghost_per_90": .10, "xgi_per_90": .15, "projected_minutes": .10, "data_confidence": .05},
    "Forwards": {"projected_points": .40, "fantasy_per_90": .20, "ghost_per_90": .10, "xgi_per_90": .15, "projected_minutes": .10, "data_confidence": .05},
    "Bench": {"projected_points": .55, "projected_minutes": .20, "fantasy_per_90": .15, "flexibility": .10},
    "Starting XI": {"projected_points": .45, "fantasy_per_90": .15, "ghost_per_90": .15, "xgi_per_90": .10, "projected_minutes": .10, "data_confidence": .05},
}
POSITION_ORDER = ("Defense + GK", "Midfield", "Forwards", "Bench", "Starting XI")


def _weighted_rate(frame: pd.DataFrame, total: str) -> float:
    values = pd.to_numeric(frame.get(total), errors="coerce")
    minutes = pd.to_numeric(frame.get("minutes_2526"), errors="coerce")
    valid = values.notna() & minutes.gt(0)
    return float(values[valid].sum() * 90 / minutes[valid].sum()) if valid.any() else np.nan


def _group_metrics(frame: pd.DataFrame, bench: bool = False) -> dict[str, float]:
    return {
        "projected_points": pd.to_numeric(frame.get("projected_points"), errors="coerce").sum(min_count=1),
        "fantasy_per_90": _weighted_rate(frame, "total_fantasy_points"),
        "ghost_per_90": _weighted_rate(frame, "ghost_points"),
        "xgi_per_90": _weighted_rate(frame, "xgi"),
        "projected_minutes": pd.to_numeric(frame.get("projected_minutes_share"), errors="coerce").mean(),
        "data_confidence": pd.to_numeric(frame.get("data_confidence"), errors="coerce").mean(),
        "flexibility": frame.get("fantrax_position", pd.Series(dtype=str)).map(
            lambda value: len(set(normalize_fantrax_positions(value).split("/")) - {""})
        ).mean() if bench else np.nan,
        "players": int(len(frame)),
    }


def _quality_label(rank: int) -> str:
    return "Elite" if rank <= 2 else "Strong" if rank <= 4 else "League Average" if rank <= 8 else "Below Average" if rank <= 10 else "Weak"


def _pick_callouts(team: pd.DataFrame, all_picks: pd.DataFrame) -> tuple[dict[str, Any], dict[str, Any]]:
    """Select transparent poster-only value and reach callouts from frozen fields."""
    work = team.copy()
    draft_scores = pd.to_numeric(all_picks.get("draft_score"), errors="coerce")
    minimum_quality = float(draft_scores.quantile(.25))
    percentiles = {
        "adp": pd.to_numeric(all_picks.get("pick_vs_adp"), errors="coerce").rank(method="average", pct=True),
        "rank": pd.to_numeric(all_picks.get("pick_vs_draft_rank"), errors="coerce").rank(method="average", pct=True),
        "quality": draft_scores.rank(method="average", pct=True),
    }
    work["_adp_value"] = pd.to_numeric(work.get("pick_vs_adp"), errors="coerce").where(pd.to_numeric(work.get("adp"), errors="coerce").notna())
    work["_rank_value"] = pd.to_numeric(work.get("pick_vs_draft_rank"), errors="coerce").where(pd.to_numeric(work.get("fantrax_overall_rank"), errors="coerce").notna())
    work["_draft_score"] = pd.to_numeric(work.get("draft_score"), errors="coerce")
    resolved = ~work.get("match_method", pd.Series("", index=work.index)).fillna("").eq("Unresolved")
    eligible = resolved & work["_draft_score"].ge(minimum_quality) & (work["_adp_value"].gt(0) | work["_rank_value"].gt(0))
    scored = work[eligible].copy()
    if scored.empty:
        scored = work[resolved & (work["_adp_value"].notna() | work["_rank_value"].notna())].copy()
    for key, source in (("adp", "_adp_value"), ("rank", "_rank_value")):
        scored[f"_{key}_pct"] = percentiles[key].reindex(scored.index)
    scored["_quality_pct"] = percentiles["quality"].reindex(scored.index)
    weighted = scored[["_adp_pct", "_rank_pct", "_quality_pct"]].mul([.50, .30, .20])
    available_weights = scored[["_adp_pct", "_rank_pct", "_quality_pct"]].notna().mul([.50, .30, .20]).sum(axis=1)
    scored["_best_score"] = weighted.sum(axis=1).div(available_weights)
    best = scored.sort_values(["_best_score", "_draft_score", "overall_pick"], ascending=[False, False, True], kind="stable").iloc[0]
    best_uses_adp = pd.notna(best["_adp_value"])
    best_value = float(best["_adp_value"] if best_uses_adp else best["_rank_value"])
    best_ref = "ADP" if best_uses_adp else "Draft HQ rank"

    reach = work[resolved].copy()
    reach["_reference_difference"] = reach["_adp_value"].combine_first(reach["_rank_value"])
    reach = reach[reach["_reference_difference"].notna()].sort_values(["_reference_difference", "overall_pick"], kind="stable").iloc[0]
    reach_uses_adp = pd.notna(reach["_adp_value"])
    reach_ref = "ADP" if reach_uses_adp else "Draft HQ rank"
    player_field = "player" if "player" in work else "drafted_player"
    def details(row: pd.Series, reason: str) -> dict[str, Any]:
        return {"player": str(row[player_field]), "round": int(row["round"]), "pick": int(row["pick_in_round"]), "reason": reason}
    return (
        {**details(best, f"+{best_value:.0f} picks versus {best_ref}"), "adp_value": best["_adp_value"], "rank_value": best["_rank_value"]},
        {**details(reach, f"{abs(float(reach['_reference_difference'])):.0f} picks before {reach_ref}"), "difference": float(reach["_reference_difference"]), "adp_difference": reach["_adp_value"]},
    )


def build_poster_profiles(managers: pd.DataFrame, picks: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return manager radar/card data and long position-group rankings."""
    share = build_share_summary(managers, picks).set_index("manager")
    manager_rows, group_rows = [], []
    for manager_row in managers.sort_values(["overall_rank", "manager"]).itertuples():
        team = picks[picks["manager"].eq(manager_row.manager)]
        xi, bench = best_legal_xi(team)
        group_frames = {
            "Defense + GK": xi[xi["canonical_position"].isin(["G", "D"])],
            "Midfield": xi[xi["canonical_position"].eq("M")],
            "Forwards": xi[xi["canonical_position"].eq("F")],
            "Bench": bench,
            "Starting XI": xi,
        }
        for label, assigned in group_frames.items():
            group_rows.append({"manager": manager_row.manager, "group": label, **_group_metrics(assigned), "player_indices": tuple(assigned.index)})
            if label == "Bench": group_rows[-1].update(_group_metrics(assigned, bench=True))
        s = share.loc[manager_row.manager]
        xi_minutes = pd.to_numeric(xi.get("projected_minutes_share"), errors="coerce")
        outlook = xi.get("minutes_outlook", pd.Series("", index=xi.index)).fillna("")
        best, reach = _pick_callouts(team, picks)
        manager_rows.append({"manager": manager_row.manager, "rank": int(manager_row.overall_rank), "grade": manager_row.letter_grade,
            "league_relative_score": manager_row.league_relative_score, "projected_starting_xi_points": s.projected_starting_xi_points,
            "draft_value": manager_row.average_pick_vs_adp, "fantasy_points_per_90": s.fantasy_points_per_90,
            "ghost_points_per_90": s.ghost_points_per_90, "xgi_per_90": manager_row.xgi_per_90,
            "starting_xi_minutes_pct": xi_minutes.mean(), "starting_xi_minutes_coverage": int(xi_minutes.notna().sum()),
            "starting_xi_minutes_low_coverage": int(xi_minutes.notna().sum()) < MIN_XI_MINUTES_COVERAGE,
            "locked_starters": int(outlook.eq("Locked Starter").sum()), "likely_starters": int(outlook.eq("Likely Starter").sum()),
            "rotation_unknown_starters": int((~outlook.isin(["Locked Starter", "Likely Starter"])).sum()),
            "best_pick": best["player"], "best_pick_round": best["round"], "best_pick_pick": best["pick"], "best_pick_reason": best["reason"],
            "best_pick_adp_value": best["adp_value"], "best_pick_rank_value": best["rank_value"],
            "biggest_reach": reach["player"], "biggest_reach_round": reach["round"], "biggest_reach_pick": reach["pick"], "biggest_reach_reason": reach["reason"],
            "biggest_reach_difference": reach["difference"], "biggest_reach_adp_difference": reach["adp_difference"],
            "xi_indices": tuple(xi.index), "bench_indices": tuple(bench.index)})
    profiles, groups = pd.DataFrame(manager_rows), pd.DataFrame(group_rows)
    for field in RADAR_FIELDS:
        values = pd.to_numeric(profiles[field], errors="coerce")
        profiles[f"{field}_rank"] = values.rank(method="min", ascending=False).astype("Int64")
        profiles[f"{field}_percentile"] = values.rank(method="average", pct=True).mul(100)
    score_parts = []
    for (group_name, metric), weight in ((key, weight) for group, weights in POSITION_WEIGHTS.items() for key, weight in [((group, metric), weight) for metric, weight in weights.items()]):
        mask = groups["group"].eq(group_name)
        percentile = pd.Series(np.nan, index=groups.index)
        percentile.loc[mask] = pd.to_numeric(groups.loc[mask, metric], errors="coerce").rank(method="average", pct=True).mul(100)
        groups[f"{metric}_percentile"] = groups.get(f"{metric}_percentile", pd.Series(np.nan, index=groups.index)).combine_first(percentile)
        score_parts.append(percentile.fillna(0).mul(weight).where(mask, 0))
    groups["strength_score"] = pd.concat(score_parts, axis=1).sum(axis=1)
    groups["league_rank"] = groups.groupby("group")["strength_score"].rank(method="min", ascending=False).astype("Int64")
    groups["league_percentile"] = groups.groupby("group")["strength_score"].rank(method="average", pct=True).mul(100)
    groups["quality_label"] = groups["league_rank"].map(lambda value: _quality_label(int(value)))
    rank_pivot = groups.pivot(index="manager", columns="group", values="league_rank")
    def tags(row: pd.Series) -> str:
        items=[]
        if row["projected_starting_xi_points_rank"] == 1: items.append("Highest Projection")
        if row["ghost_points_per_90_rank"] <= 3: items.append("High Floor")
        if row["xgi_per_90_rank"] <= 3: items.append("Attack Heavy")
        if row["draft_value_rank"] == 1: items.append("Best Value")
        if row["starting_xi_minutes_pct_rank"] <= 3: items.append("Minutes Secure")
        elif row["starting_xi_minutes_pct_rank"] >= 10: items.append("Rotation Risk")
        for group, label in (("Midfield","Elite Midfield"),("Forwards","Elite Forward Unit"),("Defense + GK","Strong Defense"),("Bench","Strong Bench")):
            if rank_pivot.at[row.manager, group] <= 2: items.append(label)
        if rank_pivot.at[row.manager, "Bench"] >= 10: items.append("Thin Bench")
        if not items: items.append("Balanced Roster")
        return " | ".join(items[:4])
    profiles["team_tags"] = profiles.apply(tags, axis=1)
    return profiles.sort_values(["rank", "manager"]), groups.sort_values(["manager", "group"])


def build_poster_audit(managers: pd.DataFrame, picks: pd.DataFrame) -> pd.DataFrame:
    profiles, groups = build_poster_profiles(managers, picks)
    ranks = groups.pivot(index="manager", columns="group", values="league_rank")
    audit = profiles.set_index("manager")[["projected_starting_xi_points", "starting_xi_minutes_pct", "starting_xi_minutes_coverage", "locked_starters", "likely_starters", "best_pick", "best_pick_adp_value", "best_pick_rank_value", "biggest_reach", "biggest_reach_adp_difference"]].join(ranks)
    return audit.reset_index().rename(columns={"projected_starting_xi_points": "projected_xi_points", "Defense + GK": "defense_gk_rank", "Midfield": "midfield_rank", "Forwards": "forward_rank", "Bench": "bench_rank", "Starting XI": "starting_xi_rank"})


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [Path("C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf")]
    for path in candidates:
        if path.exists(): return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _radar(draw: ImageDraw.ImageDraw, center: tuple[int, int], radius: int, values: list[float]) -> None:
    angles = [(-np.pi / 2) + index * 2 * np.pi / 6 for index in range(6)]
    for level in (.25, .5, .75, 1):
        points=[(center[0]+radius*level*np.cos(a),center[1]+radius*level*np.sin(a)) for a in angles]
        draw.polygon(points, outline="#cbd5e1", width=2)
    for angle in angles: draw.line([center,(center[0]+radius*np.cos(angle),center[1]+radius*np.sin(angle))],fill="#dbe3ee",width=2)
    points=[(center[0]+radius*(v/100)*np.cos(a),center[1]+radius*(v/100)*np.sin(a)) for a,v in zip(angles,values)]
    draw.polygon(points, fill="#4f7fc880", outline="#24549a", width=4)
    for point in points: draw.ellipse([point[0]-5,point[1]-5,point[0]+5,point[1]+5],fill="#173f78")


def render_poster(managers: pd.DataFrame, picks: pd.DataFrame, size: tuple[int, int] = POSTER_SIZE) -> Image.Image:
    profiles, groups = build_poster_profiles(managers, picks)
    image=Image.new("RGB",size,"#eef3f8"); draw=ImageDraw.Draw(image,"RGBA")
    draw.rectangle([0,0,size[0],210],fill="#132238"); draw.text((70,42),"2026/27 League Draft Rankings",font=_font(62,True),fill="white")
    draw.text((72,125),"12 managers · 180 picks · frozen draft-day projections",font=_font(28),fill="#c9d5e6")
    margin,gap,top=55,24,235; card_w=(size[0]-2*margin-2*gap)//3; card_h=(size[1]-top-55-3*gap)//4
    for card_index,row in enumerate(profiles.itertuples()):
        col,row_index=card_index%3,card_index//3; x=margin+col*(card_w+gap); y=top+row_index*(card_h+gap)
        border="#c89b31" if row.rank<=3 else "#cbd5e1"; draw.rounded_rectangle([x,y,x+card_w,y+card_h],radius=20,fill="white",outline=border,width=5 if row.rank<=3 else 2)
        draw.text((x+22,y+18),f"#{row.rank}  {row.manager}",font=_font(30,True),fill="#142238")
        grade_box=[x+card_w-125,y+12,x+card_w-20,y+70]; draw.rounded_rectangle(grade_box,radius=12,fill="#142238"); draw.text((x+card_w-108,y+20),f"{row.grade}",font=_font(30,True),fill="white")
        draw.text((x+24,y+62),f"League score {row.league_relative_score:.1f}",font=_font(20),fill="#52647a")
        radar_center=(x+185,y+235); _radar(draw,radar_center,105,[float(getattr(row,f"{field}_percentile")) for field in RADAR_FIELDS])
        label_positions=((0,-132),(118,-50),(105,82),(0,135),(-118,82),(-130,-50))
        for label,(dx,dy) in zip(("XI","Value","FP90","Ghost","xGI","XI Min"),label_positions): draw.text((radar_center[0]+dx-25,radar_center[1]+dy),label,font=_font(16,True),fill="#53657c")
        stats=(("Proj XI",f"{row.projected_starting_xi_points:,.0f}"),("Draft Value",f"{row.draft_value:+.1f} picks"),("Fantasy/90",f"{row.fantasy_points_per_90:.1f}"),("Ghost/90",f"{row.ghost_points_per_90:.1f}"),("xGI/90",f"{row.xgi_per_90:.2f}"),("XI Minutes",f"{row.starting_xi_minutes_pct:.1f}%"))
        sx,sy=x+355,y+112
        for idx,(label,value) in enumerate(stats): draw.text((sx,sy+idx*38),label,font=_font(18),fill="#65758a"); draw.text((sx+150,sy+idx*38),value,font=_font(19,True),fill="#18263a")
        manager_groups=groups[groups["manager"].eq(row.manager)].set_index("group")
        by=y+390
        for idx,group in enumerate(POSITION_ORDER):
            item=manager_groups.loc[group]; yy=by+idx*43
            draw.text((x+24,yy),group,font=_font(17,True),fill="#29394e"); draw.rounded_rectangle([x+145,yy+4,x+410,yy+20],radius=8,fill="#e2e8f0")
            draw.rounded_rectangle([x+145,yy+4,x+145+265*float(item.league_percentile)/100,yy+20],radius=8,fill="#4f7fc8")
            draw.text((x+425,yy-2),f"#{int(item.league_rank)} of 12 · {item.quality_label}",font=_font(16),fill="#48596f")
        tags=row.team_tags.replace(" | ","  ·  "); draw.text((x+24,y+card_h-92),tags,font=_font(16,True),fill="#24549a")
        draw.text((x+24,y+card_h-64),f"Best Pick: {row.best_pick} — R{row.best_pick_round}, P{row.best_pick_pick}",font=_font(15),fill="#1e6b42")
        draw.text((x+24,y+card_h-43),row.best_pick_reason,font=_font(14),fill="#52705f")
        draw.text((x+card_w//2,y+card_h-64),f"Biggest Reach: {row.biggest_reach} — R{row.biggest_reach_round}, P{row.biggest_reach_pick}",font=_font(15),fill="#8d3e36")
        draw.text((x+card_w//2,y+card_h-43),row.biggest_reach_reason,font=_font(14),fill="#805d59")
    return image


def poster_png_bytes(managers: pd.DataFrame, picks: pd.DataFrame) -> bytes:
    buffer=BytesIO(); render_poster(managers,picks).save(buffer,format="PNG",optimize=False); return buffer.getvalue()


def poster_output_bytes(managers: pd.DataFrame, picks: pd.DataFrame) -> tuple[bytes, bytes]:
    image=render_poster(managers,picks); png=BytesIO(); pdf=BytesIO()
    image.save(png,format="PNG",optimize=False); image.save(pdf,format="PDF",resolution=150.0)
    return png.getvalue(), pdf.getvalue()


def save_poster_outputs(managers: pd.DataFrame, picks: pd.DataFrame, png_path: Path, pdf_path: Path | None = None, audit_path: Path | None = None) -> None:
    image=render_poster(managers,picks); png_path.parent.mkdir(parents=True,exist_ok=True); image.save(png_path,format="PNG",optimize=False)
    if pdf_path is not None: image.save(pdf_path,format="PDF",resolution=150.0)
    if audit_path is not None: build_poster_audit(managers, picks).to_csv(audit_path, index=False)
