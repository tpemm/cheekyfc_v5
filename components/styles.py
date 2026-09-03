"""Central, conservatively scoped application CSS."""
from components.design_tokens import css_variables

def global_css() -> str:
    return f"""<style>
:root {{ {css_variables()}; }}
.stApp {{ background:var(--ft-app-background); color:var(--ft-text-primary); }}
.block-container {{ max-width:var(--ft-page-max-width); padding:3.75rem var(--ft-page-padding) 3rem; }}
[data-testid="stSidebar"] {{ border-right:1px solid var(--ft-border); }}
[data-testid="stSidebar"] [data-testid="stRadio"] label {{ padding:.24rem .4rem; border-radius:var(--ft-control-radius); }}
[data-testid="stMetric"] {{ background:var(--ft-card-background); border:1px solid var(--ft-border); border-radius:var(--ft-card-radius); padding:.75rem .9rem; }}
[data-testid="stMetric"] {{ min-height:88px; display:flex; flex-direction:column; justify-content:center; }}
[data-testid="stMetricLabel"] {{ color:var(--ft-text-secondary); font-size:var(--ft-metric-label); }}
[data-testid="stMetricValue"] {{ color:var(--ft-text-primary); font-size:var(--ft-metric-value); }}
[data-testid="stAlert"] {{ border-radius:var(--ft-card-radius); }}
[data-testid="stDataFrame"] {{ border:1px solid var(--ft-border); border-radius:var(--ft-control-radius); overflow:hidden; }}
[data-testid="stTabs"] [data-baseweb="tab-list"] {{ gap:.25rem; border-bottom:1px solid var(--ft-border); }}
[data-testid="stTabs"] [data-baseweb="tab"] {{ padding:.55rem .8rem; }}
[data-testid="stTabs"] [aria-selected="true"] {{ color:var(--ft-accent); font-weight:750; border-bottom-color:var(--ft-accent); }}
.ft-shell-header,.ft-page-header {{ display:flex; justify-content:space-between; align-items:flex-start; gap:1rem; }}
.ft-shell-header {{ margin:0 0 1.25rem; padding:.75rem 1rem; border:1px solid var(--ft-border); border-radius:var(--ft-card-radius); background:var(--ft-card-background); }}
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
.player-identity {{ display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:.9rem 1rem;margin:.15rem 0 .7rem;background:var(--ft-card-background);border:1px solid var(--ft-border);border-radius:var(--ft-card-radius); }}
.player-name {{ font-size:1.65rem;font-weight:800;letter-spacing:-.025em;line-height:1.05; }} .player-club {{ color:var(--ft-text-secondary);font-size:.86rem;margin-top:.25rem; }}
.player-owner {{ text-align:right;color:var(--ft-text-secondary);font-size:.8rem; }} .player-owner b {{ display:block;color:var(--ft-text-primary);font-size:.92rem; }}
.chip-row {{ display:flex;flex-wrap:wrap;gap:.35rem;margin:.15rem 0 .75rem; }} .research-chip {{ display:inline-flex;padding:.22rem .52rem;border:1px solid var(--ft-muted-border);border-radius:999px;background:var(--ft-elevated-surface);font-size:.72rem;font-weight:700;color:var(--ft-text-secondary); }}
.profile-card-title {{ font-size:.95rem;font-weight:800;margin:.2rem 0 0; }} .profile-card-copy {{ min-height:1.25rem;color:var(--ft-text-muted);font-size:.72rem;margin:.08rem 0 .15rem; }}
.trend-stack {{ display:grid;gap:.55rem;margin-top:.55rem; }} .trend-item {{ border-top:1px solid var(--ft-border);padding-top:.48rem; }} .trend-item:first-child{{border-top:0;padding-top:0}} .trend-item span{{display:block;color:var(--ft-text-muted);font-size:.68rem;text-transform:uppercase;letter-spacing:.05em}} .trend-item b{{display:block;font-size:.9rem;margin-top:.12rem}} .trend-note{{font-size:.7rem;color:var(--ft-text-muted);margin-top:.35rem}}
.fixture-grid {{ display:grid;grid-template-columns:repeat(5,minmax(105px,1fr));gap:.5rem;margin:.5rem 0 1rem; }} .fixture-card {{ border:1px solid var(--ft-border);border-radius:var(--ft-control-radius);background:var(--ft-card-background);padding:.62rem .7rem;min-height:72px; }} .fixture-card span,.fixture-card small{{display:block;color:var(--ft-text-muted);font-size:.68rem}} .fixture-card b{{display:block;font-size:.82rem;margin:.18rem 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}} .player-empty-inline{{color:var(--ft-text-muted);font-size:.8rem;padding:.7rem 0}}
.overview-toggle [data-testid="stToggle"] {{ margin:.1rem 0 .4rem; }}
@media(max-width:1100px) {{ .fixture-grid{{grid-template-columns:repeat(3,1fr)}} }}
@media(max-width:800px) {{ .block-container{{padding-left:.8rem;padding-right:.8rem}} .ft-shell-header,.ft-page-header{{flex-direction:column}} .ft-meta{{text-align:left;white-space:normal}} .ft-page-title{{font-size:1.65rem}} }}
@media(max-width:640px) {{ .player-identity{{align-items:flex-start;flex-direction:column}} .player-owner{{text-align:left}} .fixture-grid{{grid-template-columns:repeat(2,1fr)}} [data-testid="stMetric"]{{min-height:78px}} }}
</style>"""
