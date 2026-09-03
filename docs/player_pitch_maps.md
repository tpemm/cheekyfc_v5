# Player pitch maps

Player Pitch renders pre-normalized 0–100, acting-team left-to-right WhoScored event coordinates. Supported layers are Event Activity Density, Passes, Key Passes, Crosses, TakeOns, Shots, Defensive Actions, Recoveries, and Aerials. Season, Last 10, Last 5, and individual-match windows are supported.

Pass lines are drawn only when end coordinates exist. TakeOns are points, never invented carry paths. Shot markers do not receive Understat xG because exact cross-provider shot mapping is not established. These are recorded Event Activity maps, not tracking heatmaps.
