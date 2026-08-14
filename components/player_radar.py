"""Reusable 4–8 axis player radar and exact-value panels."""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
from components.charts import apply_chart_theme
from components.design_tokens import COLORS

PALETTE=(COLORS["accent"],COLORS["positive"],COLORS["warning"],COLORS["negative"],COLORS["above_average"])

def build_player_radar(records):
    valid=[r for r in records if sum(pd.notna(m["percentile"]) for m in r["metrics"])>=4]
    if not valid: return None
    figure=go.Figure()
    for i,record in enumerate(valid):
        metrics=record["metrics"]; theta=[m["label"] for m in metrics]; values=[m["percentile"] if pd.notna(m["percentile"]) else None for m in metrics]
        hover=[f"{m['label']}<br>{m['formatted']}<br>{m['percentile']:.0f}th percentile · #{int(m['rank'])} of {m['peer_count']}<br>{m['peer_group']} · {m['source']}" if pd.notna(m["percentile"]) else f"{m['label']}<br>Not available" for m in metrics]
        figure.add_trace(go.Scatterpolar(r=values+[values[0]],theta=theta+[theta[0]],name=record["player_name"],mode="lines+markers",line={"color":PALETTE[i%len(PALETTE)],"width":2},marker={"size":6},fill="toself" if len(valid)<=3 else None,fillcolor=_rgba(PALETTE[i%len(PALETTE)],.10),text=hover+[hover[0]],hovertemplate="%{text}<extra></extra>",connectgaps=False))
    figure.update_layout(polar={"radialaxis":{"range":[0,100],"tickvals":[20,40,60,80,100],"gridcolor":COLORS["chart_grid"]},"angularaxis":{"gridcolor":COLORS["chart_grid"]}},showlegend=len(valid)>1)
    return apply_chart_theme(figure,height=430)

def raw_values_frame(records):
    rows=[]
    for record in records:
        for metric in record["metrics"]:
            rows.append({"Player":record["player_name"],"Metric":metric["label"],"Raw Value":metric["formatted"],"Percentile":"—" if pd.isna(metric["percentile"]) else f"{metric['percentile']:.0f}th","Rank":"—" if pd.isna(metric["rank"]) else f"#{int(metric['rank'])} of {metric['peer_count']}","Peer Group":metric["peer_group"],"Source":metric["source"]})
    return pd.DataFrame(rows)

def comparison_values_frame(records):
    """Wide exact-value table with a restrained dot on the best valid percentile."""
    if not records: return pd.DataFrame()
    rows=[]
    for index,metric in enumerate(records[0]["metrics"]):
        candidates=[record["metrics"][index]["percentile"] for record in records]
        valid=[value for value in candidates if pd.notna(value)]; best=max(valid) if valid else None
        row={"Metric":metric["label"]}
        for record,value in zip(records,candidates):
            item=record["metrics"][index]; marker="● " if best is not None and pd.notna(value) and value==best else ""
            row[record["player_name"]]=f"{marker}{item['formatted']} · {item['percentile']:.0f}th" if pd.notna(value) else "—"
        rows.append(row)
    return pd.DataFrame(rows)

def _rgba(hex_color,alpha):
    value=hex_color.lstrip("#"); r,g,b=(int(value[i:i+2],16) for i in (0,2,4)); return f"rgba({r},{g},{b},{alpha})"
