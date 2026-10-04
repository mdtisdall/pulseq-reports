"""The options that more than one card shares, or that a plugin's card can use.

Each object is named as the builder keyword that it stands for (decision 15 of
`docs/plans/public-api.md`), and its default is the default of that keyword. A card's
`CardSpec` lists the objects that its `build` reads; a plugin that uses one of these
options imports its object. An uppercase name in another module is a default value, for
example `rf_exposure.B1RMS_WINDOW_S`.
"""

import math
from collections.abc import Mapping
from pathlib import Path

from .grad_limits import HardwareLimits
from .registry import Flag, Option, OptionCli
from .rf_exposure import B1RMS_WINDOW_S

COMMAND_LINE_LABEL = "command line"
CONFIG_FILE_LABEL = "config file"


def _positive(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{name} must be a number: {value!r}")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite number above 0: {value!r}")
    return float(value)


def _limits_from_flags(values: Mapping[str, object]) -> HardwareLimits:
    if "max_grad" not in values or "max_slew" not in values:
        raise ValueError("--max-grad and --max-slew go together: give both or neither")
    return HardwareLimits(
        max_grad_mt_per_m=_positive("--max-grad", values["max_grad"]),
        max_slew_t_per_m_per_s=_positive("--max-slew", values["max_slew"]),
        label=COMMAND_LINE_LABEL,
    )


def _limits_from_config(value: object, base_dir: Path) -> HardwareLimits:
    required = ("max_grad_mt_per_m", "max_slew_t_per_m_per_s")
    if not isinstance(value, Mapping):
        raise TypeError(f"limits must be a table with the keys {required} and label: {value!r}")
    unknown = sorted(set(value) - {*required, "label"})
    missing = [key for key in required if key not in value]
    if unknown or missing:
        raise ValueError(
            f"limits needs the keys {required} and can have label; unknown keys: {unknown}, "
            f"missing keys: {missing}"
        )
    label = value.get("label", CONFIG_FILE_LABEL)
    if not isinstance(label, str):
        raise TypeError(f"the label of limits must be text: {label!r}")
    return HardwareLimits(
        max_grad_mt_per_m=_positive("max_grad_mt_per_m", value["max_grad_mt_per_m"]),
        max_slew_t_per_m_per_s=_positive("max_slew_t_per_m_per_s", value["max_slew_t_per_m_per_s"]),
        label=label,
    )


def _gradient_asc_from_config(value: object, base_dir: Path) -> Path:
    if not isinstance(value, str):
        raise TypeError(f"gradient_asc must be a path: {value!r}")
    return base_dir / value  # an absolute path replaces base_dir


gradient_asc = Option(
    "gradient_asc",
    Path,
    None,
    "The gradient .asc file of the scanner, for the PNS prediction (without it, there is no "
    "PNS prediction and no PNS lane).",
    cli=OptionCli(
        flags=(
            Flag(
                "--gradient-asc",
                Path,
                "The gradient .asc file of the scanner, for the PNS prediction (without it, "
                "there is no PNS prediction and no PNS lane).",
                metavar="PATH",
            ),
        ),
        from_flags=lambda values: values["gradient_asc"],
        from_config=_gradient_asc_from_config,
    ),
)

limits = Option(
    "limits",
    HardwareLimits,
    None,
    "The gradient limits that the gradient limits card compares with: both --max-grad and "
    "--max-slew, or neither (without them, the card has no percent columns).",
    cli=OptionCli(
        flags=(
            Flag(
                "--max-grad",
                float,
                "The gradient amplitude limit (mT/m). Needs --max-slew.",
                metavar="MT_PER_M",
            ),
            Flag(
                "--max-slew",
                float,
                "The gradient slew rate limit (T/m/s). Needs --max-grad.",
                metavar="T_PER_M_PER_S",
            ),
        ),
        from_flags=_limits_from_flags,
        from_config=_limits_from_config,
    ),
)

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
    "Add the PNS lane to the sequence diagram (it runs the SAFE model, and needs gradient_asc).",
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
