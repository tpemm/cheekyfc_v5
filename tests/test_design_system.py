from pathlib import Path
from components.design_tokens import COLORS, SIZING, SPACING, TYPOGRAPHY
from components.charts import apply_chart_theme, position_rank_axis
from components.presentation import empty_state, metric_card, page_header, percentile_bar, status_badge
import plotly.graph_objects as go

class UI:
    def __init__(self): self.values=[]
    def markdown(self, value, **kwargs): self.values.append(value)

def test_required_semantic_tokens_are_centralized():
    required={"app_background","card_background","elevated_surface","border","text_primary","text_secondary","text_muted","accent","accent_hover","positive","above_average","neutral","warning","negative","missing_data","chart_grid","table_header","selected_row"}
    assert required <= COLORS.keys(); assert SPACING and SIZING and TYPOGRAPHY

def test_shared_components_render_content_and_missing_states():
    ui=UI(); page_header(ui,"Players","Find a player",eyebrow="Database",badge="Live")
    metric_card(ui,"Projection",None,trend="Stable",rank="#3")
    empty_state(ui,"Not available","Expected before GW1",action="Refresh League")
    output="".join(ui.values)
    assert all(value in output for value in ("Players","Projection","—","Refresh League"))

def test_badges_and_percentiles_include_text_not_only_color():
    for status in ("Live","Healthy","Available","Rostered","Free Agent","Active","Reserve","IR","Tier 1","Drafted","Added","Dropped","Pending Review"):
        assert status in status_badge(status)
    assert "#4" in percentile_bar("Projection",82,rank="#4")
    assert "—" in percentile_bar("Projection",None)

def test_shared_plotly_theme_and_rank_axis():
    figure=position_rank_axis(apply_chart_theme(go.Figure(go.Scatter(x=[1],y=[2],text=["hover"]))))
    assert figure.layout.template.layout.paper_bgcolor == "white"
    assert figure.layout.yaxis.autorange == "reversed"
    assert figure.data[0].text == ("hover",)

def test_css_is_centralized_and_avoids_generated_classes():
    css=Path("components/styles.py").read_text(encoding="utf-8")
    assert "data-testid" in css and ".css-" not in css
