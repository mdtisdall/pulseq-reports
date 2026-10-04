import pytest
from pulseq_checks import ResultMatrix, TargetInfo, TargetProfile, read_profile
from pypulseq.utils.safe_pns_prediction import safe_example_hw


def pytest_addoption(parser):
    """Add `--collected-tests-file`, so the TESTS.md check can read this run's test
    IDs instead of collecting the test files a second time in `scripts/check`."""
    parser.addoption(
        "--collected-tests-file",
        action="store",
        default=None,
        help="write the node ID of each collected test, one per line, to this path",
    )


def pytest_collection_finish(session):
    """Write the collected node IDs to `--collected-tests-file`, if it was given."""
    path = session.config.getoption("--collected-tests-file")
    if path is None:
        return
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(f"{item.nodeid}\n" for item in session.items)


@pytest.fixture
def write_gradient_asc(tmp_path):
    """A function that writes a gradient .asc file with the PNS parameters of pypulseq's
    example hardware, with the stimulation limits and thresholds multiplied by
    `limit_scale`, and returns its path. The real .asc files are confidential.

    With `split`, it writes the layout of a scanner file: an `ASCCONV` block with CRLF line
    ends and `asCOMP[0].tName`, which includes a `_GSWD_SAFETY.asc` file with the SAFE
    parameters under `GradPatSup.Phys.PNS`."""

    def write(limit_scale: float = 1.0, name: str = "MP_GPA_TEST", split: bool = False):
        hw = safe_example_hw()
        prefix = "GradPatSup.Phys.PNS." if split else ""
        pns_lines, scale_lines = [], []
        for axis in "xyz":
            a, suffix = getattr(hw, axis), axis.upper()
            pns_lines += [
                f"{prefix}flGSWDTau{suffix}[{i}] = {getattr(a, f'tau{i + 1}')!r}" for i in range(3)
            ]
            pns_lines += [
                f"{prefix}flGSWDA{suffix}[{i}] = {getattr(a, f'a{i + 1}')!r}" for i in range(3)
            ]
            pns_lines += [
                f"{prefix}flGSWDStimulationLimit{suffix} = {a.stim_limit * limit_scale!r}",
                f"{prefix}flGSWDStimulationThreshold{suffix} = {a.stim_thresh * limit_scale!r}",
            ]
            scale_lines.append(
                f"asGPAParameters[0].sGCParameters.flGScaleFactor{suffix} = {a.g_scale!r}"
            )
        path = tmp_path / f"{name}_{limit_scale:g}.asc"
        if not split:
            path.write_text(
                "\n".join([f'asCOMP.tName = "{name}"', *pns_lines, *scale_lines]) + "\n"
            )
            return path

        def ascconv(lines):
            block = ["### ASCCONV BEGIN @Checksum=mp2:0 ###", "", *lines, "", "### ASCCONV END ###"]
            return "\r\n".join(block) + "\r\n"

        safety = path.with_name(f"{path.stem}_GSWD_SAFETY.asc")
        safety.write_bytes(ascconv(pns_lines).encode())
        main = [f'asCOMP[0].tName = "{name}"', *scale_lines, f"$INCLUDE {safety.name}"]
        path.write_bytes(ascconv(main).encode())
        return path

    return write


@pytest.fixture
def no_safe_model(monkeypatch):
    """Make each way into the SAFE PNS model raise `AssertionError`, so a test shows that
    a card does not run it: `pulseq_analysis.pns_levels.pns_levels`,
    `pulseq_analysis.pns.pns_levels_for`, `pulseq_analysis.pns.pns_prediction`, and the
    names that the PNS card and the diagram card import."""

    def raise_error(*args, **kwargs):
        raise AssertionError("the SAFE model ran")

    for target in (
        "pulseq_analysis.pns_levels.pns_levels",
        "pulseq_analysis.pns.pns_levels_for",
        "pulseq_analysis.pns.pns_prediction",
        "pulseq_reports.cards.pns.pns_prediction",
        "pulseq_reports.cards.diagram.pns_levels_for",
    ):
        monkeypatch.setattr(target, raise_error)


@pytest.fixture
def make_profile(tmp_path):
    """`make_profile(name, opts)` reads a target profile from a TOML file in `tmp_path`.
    `opts` is the text of the `[opts]` section's lines (empty for no `opts`)."""

    def make(name: str, opts: str = "") -> TargetProfile:
        section = f"[opts]\n{opts}\n" if opts else ""
        path = tmp_path / f"{name}.toml"
        path.write_text(f'format = 1\nname = "{name}"\n{section}')
        return read_profile(path)

    return make


@pytest.fixture
def make_matrix():
    """`make_matrix(names)` is a `ResultMatrix` with one target for each name and no
    results, as `run_checks` gives for a run that selects no check."""

    def make(names) -> ResultMatrix:
        targets = tuple(TargetInfo(name=name, sources={}, unused_sections=()) for name in names)
        return ResultMatrix(sequence="x.seq", package_version="0", targets=targets, results=())

    return make
