"""Small read-only review embedded in the existing manager Decisions tab."""
from fantrax.live.manager_decisions import decision_summary, final_lineup, select_window, ACTIVE_STATUSES, RESERVE_STATUSES, IR_STATUSES


def render_review(ui,canonical,transactions,lineups,teams,manager_id,outcomes=None,differences=None):
    summary,events=decision_summary(canonical,transactions,lineups,teams)
    if summary.empty:
        ui.info("No canonical lineup or imported event coverage is available.")
        return
    own=summary[summary.manager_id.astype(str).eq(str(manager_id))]
    if own.empty:return
    gw=ui.selectbox("Gameweek event history",sorted(own.gameweek.unique()),key="decision_review_gw")
    ui.caption("Canonical weekly lineup is the final decision authority. Events are descriptive context; exported gameweeks do not establish lineup-lock timing. Activity is not decision quality.")
    if outcomes is not None:
        ui.subheader("Final XI outcome")
        outcome=select_window(outcomes,manager_id,gw)
        if outcome.empty:ui.info("Finalized lineup/scoring outcomes are unavailable for this gameweek.")
        else:
            ui.dataframe(outcome[["actual_xi_points","optimal_xi_points","points_left_on_bench","lineup_efficiency_pct","bench_points_total"]].style.format({"actual_xi_points":"{:.1f}","optimal_xi_points":"{:.1f}","points_left_on_bench":"{:.1f}","lineup_efficiency_pct":"{:.1f}%","bench_points_total":"{:.1f}"}),hide_index=True,use_container_width=True)
            ui.caption("Points left on bench is optimal minus actual XI points. Bench points total is descriptive and includes all non-starters under the existing Efficiency roster eligibility rules.")
            ui.subheader("Start / sit differences")
            shown=select_window(differences,manager_id,gw)
            shown=shown[shown.decision_type.ne("CORRECT_START")]
            if shown.empty:ui.info("Actual XI matches the selected optimal XI.")
            else:ui.dataframe(shown.drop(columns=["manager_id","manager_display_name","gameweek","source"]),hide_index=True,use_container_width=True)
            ui.caption("STRUCTURAL preserves the displaced and missed player sets when a unique legal one-to-one attribution is unavailable. Equivalent optima are not evidence of manager skill.")
    ui.subheader("Final lineup")
    final=final_lineup(canonical,manager_id,gw)
    if final.empty:ui.info("No canonical final lineup is available for this gameweek.")
    else:
        for label,states in (("Active",ACTIVE_STATUSES),("Reserve",RESERVE_STATUSES),("Inj Res",IR_STATUSES)):
            ui.write(label)
            part=final[final.lineup_status.astype(str).str.upper().isin(states)]
            ui.dataframe(part[[c for c in ("fantrax_player_id","player_name","club","fantrax_position","lineup_status") if c in part]],hide_index=True,use_container_width=True)
    ui.subheader("Decision summary")
    selected=select_window(summary,manager_id,gw)
    ui.dataframe(selected[["lineup_event_count","unique_players_tinkered","repeated_tinkers","claim_count","drop_count","transaction_group_count","first_lineup_event_timestamp","last_lineup_event_timestamp"]],hide_index=True,use_container_width=True)
    ui.caption(selected.event_coverage_status.iloc[0])
    ui.subheader("Activity timeline")
    ui.caption("Candidate transaction groups associate manager and exact exported timestamp; they are not official Fantrax transaction IDs. No exported events does not prove no activity.")
    ui.dataframe(select_window(events,manager_id,gw),hide_index=True,use_container_width=True)
