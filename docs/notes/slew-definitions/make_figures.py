"""Make the figures and the numbers of docs/notes/slew-definitions.md.

Run from the repository root, in the devShell:

    nix develop --command uv run python docs/notes/slew-definitions/make_figures.py \\
        --pulseq-matlab <pulseq clone>/matlab --safe-matlab <safe_pns_prediction clone>

The README section of the report gives the commits of the two MATLAB clones. Octave
comes from PATH, or else from the locked nixpkgs of the flake (`nix shell --inputs-from .
nixpkgs#octave`). The figures are written next to this file, each in a light and a dark
version. The numbers table is printed.
"""

import argparse
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import slew_paths as sp

HERE = Path(__file__).resolve().parent
US = 1e6  # s -> us
LIMIT = 100.0  # T/m/s, SYS.max_slew

THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "ink2": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "base": "#c3c2b7",
        "limit": "#2a78d6",
        "py": "#eb6834",
        "mat": "#1baf7a",
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#ffffff",
        "ink2": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "base": "#383835",
        "limit": "#3987e5",
        "py": "#d95926",
        "mat": "#199e70",
    },
}

# The blue line is the value that the limit checks compare with max_slew. Both libraries
# compute the same value for every event in figures 1-5, except that MATLAB does not
# check a trapezoid at all; figure 7 has the one event type where the values differ.
LABEL_LIMIT = "Limit checks: segment slope"
LABEL_LIMIT_BOTH = "Limit checks, both: segment slope"
LABEL_LIMIT_PY_ONLY = "Limit check, pypulseq only: segment slope"
LABEL_JUNCTION = "Limit checks, both: junction step / Δ"
LABEL_PY = "pypulseq calc_pns: dgdt"
LABEL_MAT = "MATLAB calcPNS: dgdt"


def style(ax, th, ylabel=None):
    ax.set_facecolor(th["surface"])
    ax.grid(True, color=th["grid"], linewidth=0.8, linestyle="-")
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(th["base"])
    ax.tick_params(colors=th["ink2"], labelsize=8, length=3)
    if ylabel:
        ax.set_ylabel(ylabel, color=th["ink2"], fontsize=9)
    ax.axhline(0, color=th["base"], linewidth=0.8)


def new_figure(th, nrows, ncols, width, height, sharex="col"):
    fig, axes = plt.subplots(
        nrows,
        ncols,
        figsize=(width, height),
        sharex=sharex,
        squeeze=False,
        gridspec_kw={"hspace": 0.12, "wspace": 0.18},
    )
    fig.patch.set_facecolor(th["surface"])
    return fig, axes


def legend(fig, th, handles, ncol):
    # fig.legend fills column by column; reorder so that the entries read by rows.
    nrow = -(-len(handles) // ncol)
    grid = [handles[r * ncol : (r + 1) * ncol] for r in range(nrow)]
    handles = [row[c] for c in range(ncol) for row in grid if c < len(row)]
    leg = fig.legend(
        handles=handles,
        loc="upper center",
        ncol=ncol,
        frameon=False,
        fontsize=8,
        bbox_to_anchor=(0.5, 1.0),
        handlelength=2.4,
    )
    for text in leg.get_texts():
        text.set_color(th["ink"])


def step_polyline(segments, lo, hi):
    """A step polyline (us, T/m/s) of rows (t0, t1, value), 0 where no row is. Rows
    with a NaN value (a segment that the check does not look at) are left out."""
    xs, ys = [lo], [0.0]
    last = lo
    rows = segments[~np.isnan(segments[:, 2])]
    for t0, t1, s in sorted(rows.tolist()):
        t0, t1 = t0 * US, t1 * US
        if t0 > last:
            xs += [last, t0]
            ys += [0.0, 0.0]
        xs += [t0, t1]
        ys += [s, s]
        last = t1
    xs += [last, hi]
    ys += [0.0, 0.0]
    return np.array(xs), np.array(ys)


def plot_gradient(ax, th, r, axis, samples="both", merged=()):
    """Top panel: the event polylines, the merged waveforms that `merged` names ("py",
    "mat"), and the SAFE samples: "both" draws one set (the paths have equal samples),
    "separate" draws the samples of each path."""
    i = sp.AXES.index(axis)
    for t, g in r.limit[axis]["events"]:
        ax.plot(t * US, g * 1e3, color=th["ink2"], linewidth=2, solid_capstyle="round")
    if "py" in merged:
        t, g = r.py_wave[axis]
        ax.plot(t * US, g * 1e3, color=th["py"], linewidth=1.25)
    if "mat" in merged:
        w = r.mat[f"gw_{axis}"]
        ax.plot(w[0] * US, w[1] / sp.GAMMA * 1e3, color=th["mat"], linewidth=1.25, ls="--")
    marker = {"marker": "o", "markersize": 5, "markeredgecolor": th["surface"], "mew": 1}
    color = th["py"] if samples == "separate" else th["ink"]
    ax.plot(r.py["t"] * US, r.py["g"][:, i] * 1e3, ls="none", color=color, **marker)
    if samples == "separate":
        ax.plot(
            r.mat["t_axis"] * US,
            r.mat["gwr"][:, i] / sp.GAMMA * 1e3,
            ls="none",
            color=th["mat"],
            **dict(marker, markersize=3.5),
        )


def plot_slew(ax, th, r, axis, lo, hi, split=False):
    """Bottom panel: the limit-check slew, and the dgdt of both PNS paths, each drawn
    over the raster interval that it covers. The limit-check line is pypulseq's value
    (column 3 of the segment rows). With split, MATLAB's value (column 4) is drawn solid
    and pypulseq's dotted, for an event where they differ."""
    i = sp.AXES.index(axis)
    seg = r.limit[axis]["segments"]
    end = r.py["t"][-1] * US + 100
    if split:
        xs, ys = step_polyline(seg[:, [0, 1, 4]], 0.0, end)
        ax.plot(xs, ys, color=th["limit"], linewidth=2.5, solid_joinstyle="miter")
        xs, ys = step_polyline(seg[:, [0, 1, 3]], 0.0, end)
        ax.plot(xs, ys, color=th["limit"], linewidth=2.5, ls=(0, (1, 1.5)))
    else:
        xs, ys = step_polyline(seg[:, [0, 1, 3]], 0.0, end)
        ax.plot(xs, ys, color=th["limit"], linewidth=2.5, solid_joinstyle="miter")
    jn = r.limit[axis]["junctions"]
    jn = jn[np.abs(jn[:, 1]) > 1e-6]
    ax.plot(
        jn[:, 0] * US,
        jn[:, 1],
        ls="none",
        marker="D",
        markersize=6,
        color=th["limit"],
        markeredgecolor=th["surface"],
        mew=1.2,
        zorder=5,
    )
    t = r.py["t"] * US
    ax.stairs(r.py["dgdt"][:, i], np.r_[t[0] - sp.DT * US, t], color=th["py"], linewidth=1.75)
    tm = np.atleast_1d(r.mat["t_axis"]) * US
    dm = np.atleast_2d(r.mat["dgdt"])[i]
    ax.stairs(dm, np.r_[tm, tm[-1] + sp.DT * US], color=th["mat"], linewidth=1.75, ls=(0, (3, 2)))
    for y in (LIMIT, -LIMIT):
        ax.axhline(y, color=th["muted"], linewidth=0.8)
    ax.text(hi, LIMIT, "max_slew ", color=th["muted"], fontsize=7, va="bottom", ha="right")


def handles(th, which, limit_label=LABEL_LIMIT):
    from matplotlib.lines import Line2D

    h = {
        "event": Line2D([], [], color=th["ink2"], lw=2, label="Gradient events"),
        "samples": Line2D(
            [], [], ls="none", marker="o", ms=5, color=th["ink"], label="SAFE samples, (k+½)Δ"
        ),
        "samples_py": Line2D(
            [], [], ls="none", marker="o", ms=5, color=th["py"], label="pypulseq samples"
        ),
        "samples_mat": Line2D(
            [], [], ls="none", marker="o", ms=3.5, color=th["mat"], label="MATLAB samples"
        ),
        "wave_py": Line2D([], [], color=th["py"], lw=1.25, label="pypulseq waveforms()"),
        "wave_mat": Line2D(
            [], [], color=th["mat"], lw=1.25, ls="--", label="MATLAB waveforms_and_times()"
        ),
        "limit": Line2D([], [], color=th["limit"], lw=2.5, label=limit_label),
        "limit_mat": Line2D(
            [], [], color=th["limit"], lw=2.5, label="Limit check, MATLAB: segment slope"
        ),
        "limit_py_os": Line2D(
            [],
            [],
            color=th["limit"],
            lw=2.5,
            ls=(0, (1, 1.5)),
            label="Limit check, pypulseq: segment slope / 4",
        ),
        "junction": Line2D(
            [], [], ls="none", marker="D", ms=6, color=th["limit"], label=LABEL_JUNCTION
        ),
        "py": Line2D([], [], color=th["py"], lw=1.75, label=LABEL_PY),
        "mat": Line2D([], [], color=th["mat"], lw=1.75, ls=(0, (3, 2)), label=LABEL_MAT),
    }
    return [h[k] for k in which]


def annotate(ax, th, x, y, text, dx=6, dy=0, ha="left"):
    ax.annotate(
        text,
        (x, y),
        xytext=(dx, dy),
        textcoords="offset points",
        color=th["ink2"],
        fontsize=7.5,
        ha=ha,
        va="center",
    )


def two_panel(
    th,
    r,
    axis,
    lo,
    hi,
    width=7.5,
    samples="both",
    merged=(),
    extra_handles=(),
    limit_label=LABEL_LIMIT,
    split=False,
):
    fig, axes = new_figure(th, 2, 1, width, 4.6)
    top, bottom = axes[0, 0], axes[1, 0]
    plot_gradient(top, th, r, axis, samples=samples, merged=merged)
    plot_slew(bottom, th, r, axis, lo, hi, split=split)
    style(top, th, "G (mT/m)")
    style(bottom, th, "slew (T/m/s)")
    bottom.set_xlim(lo, hi)
    bottom.set_xlabel("time (µs)", color=th["ink2"], fontsize=9)
    sample_keys = ["samples"] if samples == "both" else ["samples_py", "samples_mat"]
    limit_keys = ["limit_mat", "limit_py_os"] if split else ["limit", "junction"]
    keys = ["event", *sample_keys, *extra_handles, *limit_keys, "py", "mat"]
    legend(fig, th, handles(th, keys, limit_label), ncol=3)
    fig.subplots_adjust(top=0.84 if len(keys) <= 6 else 0.8, left=0.1, right=0.95, bottom=0.11)
    return fig, top, bottom


# --- The figures ------------------------------------------------------------------


def fig_trapezoid(th, res):
    fig, _top, bottom = two_panel(th, res["trap"], "x", 30, 170, limit_label=LABEL_LIMIT_PY_ONLY)
    annotate(bottom, th, 85, 50, "at a corner: the average of 100 and 0", dx=4, dy=8)
    return fig


def fig_blips(th, res):
    fig, _top, bottom = two_panel(th, res["blips"], "x", 30, 230, limit_label=LABEL_LIMIT_PY_ONLY)
    note = "one-raster ramps (left): dgdt peak 50,\nhalf the slope\ntwo-raster ramps (right): dgdt peak 100"
    annotate(bottom, th, 166, 55, note, dx=0)
    return fig


def fig_arbitrary(th, res):
    fig, _top, bottom = two_panel(th, res["arb"], "x", 30, 270, limit_label=LABEL_LIMIT_BOTH)
    note = "at each edge: a half-raster segment\nof slope 94, but dgdt 47"
    annotate(bottom, th, 160, 60, note, dx=0)
    return fig


def fig_junctions(th, res):
    cases = [
        ("junction_arb", "arbitrary → arbitrary", 110, 200),
        ("junction_ext_long", "extended trap. → extended trap.,\nfirst segment 100 µs", 110, 280),
        ("junction_ext_short", "extended trap. → extended trap.,\nfirst segment 10 µs", 110, 200),
    ]
    fig, axes = new_figure(th, 2, 3, 12, 5.0)
    for col, (name, title, lo, hi) in enumerate(cases):
        r = res[name]
        top, bottom = axes[0, col], axes[1, col]
        plot_gradient(top, th, r, "x", merged=("py",))
        plot_slew(bottom, th, r, "x", lo, hi)
        style(top, th, "G (mT/m)" if col == 0 else None)
        style(bottom, th, "slew (T/m/s)" if col == 0 else None)
        top.set_title(title, color=th["ink"], fontsize=9, loc="left")
        bottom.set_xlim(lo, hi)
        bottom.set_ylim(-115, 215)
        bottom.set_xlabel("time (µs)", color=th["ink2"], fontsize=9)
        peak = np.abs(r.py["dgdt"][:, 0]).max()
        k = int(np.argmax(np.abs(r.py["dgdt"][:, 0])))
        annotate(bottom, th, r.py["t"][k] * US - 5, peak, f"dgdt {peak:.0f}", dx=6, dy=6)
    keys = ["event", "samples", "wave_py", "limit", "junction", "py", "mat"]
    legend(fig, th, handles(th, keys, LABEL_LIMIT_BOTH), ncol=4)
    fig.subplots_adjust(top=0.8, left=0.07, right=0.95, bottom=0.1)
    return fig


def fig_no_gradient_block(th, res):
    r = res["junction_empty"]
    fig, top, _bottom = two_panel(
        th,
        r,
        "x",
        150,
        520,
        samples="separate",
        merged=("py", "mat"),
        extra_handles=("wave_py", "wave_mat"),
    )
    top.set_ylim(-0.5, 4.2)
    return fig


def fig_pns(th, res):
    r = res["epi"]
    _, _, comp, t = r.py_calc_pns
    tm, cm = np.atleast_1d(r.mat["t_pns"]), np.atleast_2d(r.mat["pns_comp"])
    fig, axes = new_figure(th, 3, 1, 7.5, 6.4, sharex=False)
    a0, a1, a2 = axes[:, 0]
    for ax, lo, hi, marker in ((a0, 0, 3400, None), (a1, 860, 960, "o")):
        kw = {"marker": marker, "markersize": 4, "markeredgecolor": th["surface"], "mew": 0.8}
        ax.plot(t * US, comp[:, 0] * 100, color=th["py"], lw=1.75, **kw)
        ax.plot(tm * US, cm[0] * 100, color=th["mat"], lw=1.75, ls=(0, (3, 2)), **kw)
        ax.set_xlim(lo, hi)
        style(ax, th, "PNS x (% of limit)")
    a1.set_ylim(32, 42)
    annotate(a1, th, 905, 41, "the same values, 10 µs apart", dx=0, dy=0, ha="center")
    kp, km = np.round(t / 5e-6).astype(int), np.round(tm / 5e-6).astype(int)
    _, ip, im = np.intersect1d(kp, km, return_indices=True)
    same = np.abs(comp[ip, 0] - cm[0, im]) * 100
    _, ip2, im2 = np.intersect1d(kp, km + 2, return_indices=True)
    shifted = np.abs(comp[ip2, 0] - cm[0, im2]) * 100
    a2.semilogy(
        tm[im] * US,
        np.maximum(same, 1e-18),
        color=th["limit"],
        lw=1.5,
        label="MATLAB(t) − pypulseq(t)",
    )
    a2.semilogy(
        tm[im2] * US,
        np.maximum(shifted, 1e-18),
        color=th["ink2"],
        lw=1.5,
        label="MATLAB(t) − pypulseq(t + 10 µs)",
    )
    a2.set_xlim(0, 3400)
    a2.set_ylim(1e-17, 1e2)
    style(a2, th, "|difference| (%)")
    a2.set_xlabel("time as each path reports it (µs)", color=th["ink2"], fontsize=9)
    leg = a2.legend(loc="center right", frameon=False, fontsize=8)
    for text in leg.get_texts():
        text.set_color(th["ink"])
    from matplotlib.lines import Line2D

    legend(
        fig,
        th,
        [
            Line2D([], [], color=th["py"], lw=1.75, label="pypulseq calc_pns"),
            Line2D([], [], color=th["mat"], lw=1.75, ls=(0, (3, 2)), label="MATLAB calcPNS"),
        ],
        ncol=2,
    )
    fig.subplots_adjust(top=0.93, left=0.1, right=0.95, bottom=0.08, hspace=0.4)
    return fig


def fig_oversampled(th, res):
    fig, _top, bottom = two_panel(
        th,
        res["arb_oversampled"],
        "x",
        30,
        190,
        samples="separate",
        merged=("py", "mat"),
        extra_handles=("wave_py", "wave_mat"),
        split=True,
    )
    bottom.set_ylim(-230, 230)
    note = "MATLAB's check: 200 (rejects)\npypulseq's check: 50 (accepts)"
    annotate(bottom, th, 118, 150, note, dx=0)
    return fig


FIGURES = {
    "fig1-trapezoid": fig_trapezoid,
    "fig2-one-raster-ramps": fig_blips,
    "fig3-arbitrary": fig_arbitrary,
    "fig4-junction-steps": fig_junctions,
    "fig5-no-gradient-block": fig_no_gradient_block,
    "fig6-pns-time-shift": fig_pns,
    "fig7-oversampled": fig_oversampled,
}


# --- The numbers ------------------------------------------------------------------


def numbers(res, table):
    rows = [
        (
            "| Example | Axis | pypulseq limit check: segments | "
            "MATLAB limit check: segments | Limit checks, both: junctions | "
            "pypulseq dgdt | MATLAB dgdt | pypulseq test report | MATLAB test report | "
            "PNS peak pypulseq | PNS peak MATLAB |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, r in res.items():
        axes = ("x", "y") if name == "epi" else ("x",)
        for axis in axes:
            i = sp.AXES.index(axis)
            seg = r.limit[axis]["segments"]
            jn = r.limit[axis]["junctions"]
            dm = np.atleast_2d(r.mat["dgdt"])[i]
            mat_seg = np.abs(seg[:, 4])
            mat_cell = "not checked" if np.all(np.isnan(mat_seg)) else f"{np.nanmax(mat_seg):.1f}"
            rows.append(
                f"| `{name}` | {axis} | {np.abs(seg[:, 3]).max():.1f} | {mat_cell} | "
                f"{np.abs(jn[:, 1]).max():.1f} | {np.abs(r.py['dgdt'][:, i]).max():.1f} | "
                f"{np.abs(dm).max():.1f} | {r.py_report_slew[i]:.1f} | "
                f"{np.atleast_1d(r.mat['report_slew'])[i]:.1f} | "
                f"{r.py_calc_pns[1].max() * 100:.3f} % | "
                f"{np.max(r.mat['pns_norm']) * 100:.3f} % |"
            )
    out = ["\n".join(rows), ""]
    out.append("| Case | pypulseq | MATLAB |")
    out.append("|---|---|---|")
    for name, row in table.items():
        cells = []
        for key in ("pypulseq", "matlab"):
            ok, msg = row[key]
            cells.append("accepts" if ok else f"rejects: {msg}")
        out.append(f"| {row['doc']} | {cells[0]} | {cells[1]} |")
    epi = res["epi"]
    old_py = epi.py_pns_norm_old.max() / epi.py_calc_pns[1].max()
    old_mat = np.max(epi.mat["pns_norm_old"]) / np.max(epi.mat["pns_norm"])
    out.append("")
    out.append(
        f"Old-layout .asc, epi: PNS peak / new-layout peak: pypulseq {old_py:.4f}, "
        f"MATLAB {old_mat:.4f}"
    )
    warnings = {n: str(r.mat["warnings"]) for n, r in res.items() if np.size(r.mat["warnings"])}
    out.append(f"MATLAB waveforms_and_times warnings: {warnings}")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pulseq-matlab", type=Path, help="the matlab/ folder of pulseq")
    parser.add_argument("--safe-matlab", type=Path, help="a safe_pns_prediction clone")
    parser.add_argument("--work", type=Path, help="work folder (default: a temporary one)")
    parser.add_argument(
        "--reuse", action="store_true", help="do not run Octave; reuse the files in --work"
    )
    args = parser.parse_args()
    if not args.reuse and (args.pulseq_matlab is None or args.safe_matlab is None):
        parser.error("--pulseq-matlab and --safe-matlab are needed unless --reuse is given")
    work = args.work or Path(tempfile.mkdtemp(prefix="slew-definitions-"))
    res, table = sp.compute(work, args.pulseq_matlab, args.safe_matlab, not args.reuse)
    plt.switch_backend("Agg")
    plt.rcParams["font.family"] = ["Helvetica Neue", "Arial", "DejaVu Sans"]
    for mode, th in THEMES.items():
        for name, make in FIGURES.items():
            fig = make(th, res)
            suffix = "" if mode == "light" else "-dark"
            fig.savefig(HERE / f"{name}{suffix}.png", dpi=150, facecolor=th["surface"])
            plt.close(fig)
    print(numbers(res, table))


if __name__ == "__main__":
    main()
