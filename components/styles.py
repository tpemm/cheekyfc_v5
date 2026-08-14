"""Central, conservatively scoped application CSS."""
from components.design_tokens import css_variables

def global_css() -> str:
    return f"""<style>
:root {{ {css_variables()}; }}
.stApp {{ background:var(--ft-app-background); color:var(--ft-text-primary); }}
.block-container {{ max-width:var(--ft-page-max-width); padding:2.75rem var(--ft-page-padding) 3rem; }}
[data-testid="stSidebar"] {{ border-right:1px solid var(--ft-border); }}
[data-testid="stSidebar"] [data-testid="stRadio"] label {{ padding:.24rem .4rem; border-radius:var(--ft-control-radius); }}
[data-testid="stMetric"] {{ background:var(--ft-card-background); border:1px solid var(--ft-border); border-radius:var(--ft-card-radius); padding:.75rem .9rem; }}
[data-testid="stMetricLabel"] {{ color:var(--ft-text-secondary); font-size:var(--ft-metric-label); }}
[data-testid="stMetricValue"] {{ color:var(--ft-text-primary); font-size:var(--ft-metric-value); }}
[data-testid="stAlert"] {{ border-radius:var(--ft-card-radius); }}
[data-testid="stDataFrame"] {{ border:1px solid var(--ft-border); border-radius:var(--ft-control-radius); overflow:hidden; }}
[data-testid="stTabs"] [data-baseweb="tab-list"] {{ gap:.25rem; border-bottom:1px solid var(--ft-border); }}
[data-testid="stTabs"] [data-baseweb="tab"] {{ padding:.55rem .8rem; }}
.ft-shell-header,.ft-page-header {{ display:flex; justify-content:space-between; align-items:flex-start; gap:1rem; }}
.ft-shell-header {{ margin:-1rem 0 1.25rem; padding:.75rem 1rem; border:1px solid var(--ft-border); border-radius:var(--ft-card-radius); background:var(--ft-card-background); }}
.ft-page-header {{ margin:.25rem 0 1.35rem; }}
.ft-eyebrow,.section-eyebrow {{ color:var(--ft-accent); font-size:var(--ft-page-eyebrow); font-weight:750; letter-spacing:.1em; text-transform:uppercase; }}
.ft-page-title {{ margin:.18rem 0; color:var(--ft-text-primary); font-size:var(--ft-page-title); font-weight:800; letter-spacing:-.025em; line-height:1.08; }}
.ft-page-subtitle,.section-copy {{ color:var(--ft-text-secondary); font-size:.88rem; max-width:760px; }}
.section-title {{ color:var(--ft-text-primary); font-size:var(--ft-section-title); font-weight:750; margin:1.55rem 0 .15rem; }}
.ft-meta {{ color:var(--ft-text-muted); font-size:var(--ft-annotation); text-align:right; white-space:nowrap; }}
.ft-card {{ background:var(--ft-card-background); border:1px solid var(--ft-border); border-radius:var(--ft-card-radius); padding:var(--ft-card-padding); }}
.ft-kpi-value {{ color:var(--ft-text-primary); font-size:var(--ft-metric-value); font-weight:800; line-height:1.15; margin:.25rem 0; }}
.ft-label {{ color:var(--ft-text-secondary); font-size:var(--ft-metric-label); font-weight:750; letter-spacing:.05em; text-transform:uppercase; }}
.ft-detail {{ color:var(--ft-text-muted); font-size:var(--ft-annotation); }}
.ft-badge {{ display:inline-flex; border-radius:999px; padding:.18rem .5rem; font-size:var(--ft-badge-text); font-weight:750; background:#edf1f4; color:var(--ft-neutral); border:1px solid var(--ft-muted-border); }}
.ft-badge-positive {{ background:#e8f3ee; color:var(--ft-positive); }} .ft-badge-warning {{ background:#fbf2e4; color:var(--ft-warning); }} .ft-badge-negative {{ background:#faeceb; color:var(--ft-negative); }} .ft-badge-accent {{ background:#e6f1f5; color:var(--ft-accent); }}
.ft-empty,.ft-notice {{ border:1px solid var(--ft-border); border-radius:var(--ft-card-radius); padding:1rem; background:var(--ft-elevated-surface); }}
.ft-empty-title {{ font-weight:750; }} .ft-empty-copy {{ color:var(--ft-text-secondary); font-size:.84rem; margin-top:.2rem; }}
.ft-percentile {{ display:grid; grid-template-columns:minmax(105px,1fr) 2.2fr auto; gap:.55rem; align-items:center; font-size:.78rem; }}
.ft-percentile-track {{ height:7px; background:var(--ft-chart-grid); border-radius:99px; overflow:hidden; }} .ft-percentile-fill {{ display:block; height:100%; background:var(--ft-accent); }}
@media(max-width:800px) {{ .block-container{{padding-left:.8rem;padding-right:.8rem}} .ft-shell-header,.ft-page-header{{flex-direction:column}} .ft-meta{{text-align:left;white-space:normal}} .ft-page-title{{font-size:1.65rem}} }}
</style>"""
