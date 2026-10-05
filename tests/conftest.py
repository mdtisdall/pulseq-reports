import pytest
from pulseq_checks import ResultMatrix, TargetInfo, TargetProfile, read_profile


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
