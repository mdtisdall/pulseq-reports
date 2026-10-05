"""The options that more than one card shares, or that a plugin's card can use.

Each object is named as the builder keyword that it stands for (decision 15 of
`docs/plans/public-api.md`), and its default is the default of that keyword. A card's
`CardSpec` lists the objects that its `build` reads; a plugin that uses one of these
options imports its object. An uppercase name in another module is a default value, for
example `rf_exposure.B1RMS_WINDOW_S`.
"""

from .registry import Option
from .rf_exposure import B1RMS_WINDOW_S

periodic = Option(
    "periodic",
    bool,
    True,
    "The sequence repeats (a period of a longer scan), for the B1+rms of the RF exposure "
    "card. With --no-periodic, it plays one time.",
)

b1rms_window_s = Option(
    "b1rms_window_s",
    float,
    B1RMS_WINDOW_S,
    "The length (s) of the averaging window of the highest B1+rms.",
)

pns_lane = Option(
    "pns_lane",
    bool,
    False,
    "Add the PNS lane to the sequence diagram (it needs targets that give SAFE parameters, "
    "and their analysis results).",
)

views = Option(
    "views",
    tuple[str, ...],
    ("profile",),
    "The views of the RF pulse profiles card, a comma list of profile, z_df and 2d. The "
    "profile view is always on.",
)

plane = Option(
    "plane",
    tuple[str, ...],
    None,
    "The two gradient axes of the 2d view of the RF pulse profiles card, a comma pair of "
    "x, y and z (default: the two axes with the largest RMS gradient).",
)

extent_m = Option(
    "extent_m",
    float,
    None,
    "The extent (m) of the 2d view of the RF pulse profiles card (default: from the FOV "
    "definition).",
)

max_rows = Option(
    "max_rows",
    int,
    500,
    "The largest number of blocks in the block table card.",
)
