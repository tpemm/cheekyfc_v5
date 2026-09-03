# Player Profile Overview

The live Overview is a compact scouting card: existing headline metrics, Mode and Percentile Basis controls, Edit Metrics, and a 3:2 radar/exact-stat row. It ends after that row; no secondary percentile-bar section is rendered.

The default radar axes are exactly Ghost / Start, Points / Start, Season Points, and Games Started. Edit Metrics preserves controlled catalog order and accepts three through eight choices. Current and historical fields remain separate; Overlay retains only shared valid axes. Invalid axes are removed rather than represented as zero. The radar component explicitly repeats the first theta and value after the final axis for 3–8 axis closure.

Exact statistics are Points / Start, Ghost / Start, Season Points, Games Started, xGI / 90, and Minutes Outlook. Current, Historical, and Overlay modes use their established fields; historical Minutes Outlook remains unavailable.

Database ordering and Overview ranks share one numeric preparation helper. It applies the same source field, missing-value handling, competition ranking (`method="min"`), and League or primary-Position universe. Missing values remain unranked and sort last.

Overview hover is deliberately terse: metric label, exact raw value, and `#N of M` rank only. Percentiles still determine polygon geometry but are not repeated in hover.
