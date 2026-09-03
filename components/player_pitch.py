"""Reusable, vertically oriented analytical football pitch."""
from __future__ import annotations

import math
import plotly.graph_objects as go

LINE = "#8da39a"


def pitch_shapes(line_color: str = LINE) -> list[dict]:
    """Return complete 0..100 pitch geometry; opponent goal is at the top."""
    line = {"color": line_color, "width": 1.5}
    shapes: list[dict] = [
        dict(type="rect", x0=0, y0=0, x1=100, y1=100, line={**line, "width": 2}),
        dict(type="line", x0=0, y0=50, x1=100, y1=50, line=line),
        dict(type="circle", x0=40, y0=43.2, x1=60, y1=56.8, line=line),
        dict(type="circle", x0=49.5, y0=49.5, x1=50.5, y1=50.5, line=line, fillcolor=line_color),
    ]
    for top in (False, True):
        y_goal, direction = (100, -1) if top else (0, 1)
        shapes.extend([
            dict(type="rect", x0=20, y0=y_goal, x1=80, y1=y_goal + direction*18, line=line),
            dict(type="rect", x0=36, y0=y_goal, x1=64, y1=y_goal + direction*6, line=line),
            dict(type="circle", x0=49.5, y0=y_goal + direction*12-.5, x1=50.5, y1=y_goal + direction*12+.5, line=line, fillcolor=line_color),
            dict(type="path", path=_penalty_arc(top), line=line),
            dict(type="rect", x0=44, y0=y_goal, x1=56, y1=y_goal-direction*2.2, line=line),
        ])
    for x, y, sx, sy in ((0,0,1,1),(100,0,-1,1),(0,100,1,-1),(100,100,-1,-1)):
        shapes.append(dict(type="path", path=_corner_arc(x,y,sx,sy), line=line))
    return shapes


def _penalty_arc(top: bool) -> str:
    cy = 88 if top else 12
    angles = range(37, 144, 8) if top else range(217, 324, 8)
    points = [(50 + 10*math.cos(math.radians(a)), cy + 6.8*math.sin(math.radians(a))) for a in angles]
    return "M " + " L ".join(f"{x:.2f},{y:.2f}" for x,y in points)


def _corner_arc(x: float, y: float, sx: int, sy: int) -> str:
    pts=[(x+sx*2*math.cos(math.radians(a)),y+sy*2*math.sin(math.radians(a))) for a in range(0,91,15)]
    return "M " + " L ".join(f"{px:.2f},{py:.2f}" for px,py in pts)


def draw_pitch(*, height: int = 650, background: str = "#f2f6f3") -> go.Figure:
    fig=go.Figure()
    fig.update_xaxes(range=[-4,104],visible=False,fixedrange=True)
    fig.update_yaxes(range=[-4,104],visible=False,fixedrange=True,scaleanchor="x",scaleratio=1)
    fig.update_layout(height=height,margin=dict(l=5,r=5,t=24,b=5),plot_bgcolor=background,paper_bgcolor="rgba(0,0,0,0)",shapes=pitch_shapes(),showlegend=False)
    return fig


def add_points(fig: go.Figure, events, *, colors, size: int = 7) -> go.Figure:
    fig.add_trace(go.Scatter(x=events.plot_x,y=events.plot_y,mode="markers",marker={"size":size,"color":colors,"opacity":.75},text=events.event_type,customdata=events[["x","y"]],hovertemplate="%{text}<br>raw x=%{customdata[0]:.1f}, y=%{customdata[1]:.1f}<extra></extra>",showlegend=False))
    return fig


def add_lines(fig: go.Figure, events) -> go.Figure:
    for event in events[events.plot_end_x.notna() & events.plot_end_y.notna()].itertuples():
        fig.add_trace(go.Scatter(x=[event.plot_x,event.plot_end_x],y=[event.plot_y,event.plot_end_y],mode="lines",line={"color":"#2f9e44" if str(event.outcome)=="Successful" else "#c92a2a","width":1},opacity=.45,hoverinfo="skip",showlegend=False))
    return fig
