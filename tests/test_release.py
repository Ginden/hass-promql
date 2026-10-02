"""Verify release validation and the actual archive installed by HACS."""

import json
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.prepare_release import prepare_release


@pytest.fixture
def release_repo(tmp_path: Path) -> Path:
    """Create a small real Git repository with a previously released version."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    component = tmp_path / "custom_components/promql"
    component.mkdir(parents=True)
    (component / "manifest.json").write_text(
        json.dumps({"domain": "promql", "version": "0.1.2"}) + "\n"
    )
    (component / "sensor.py").write_text('"""Sensor source."""\n')
    (component / "translations").mkdir()
    (component / "translations/en.json").write_text('{"title": "PromQL"}\n')
    (tmp_path / "README.md").write_text("Repository documentation.\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Release Test",
            "-c",
            "user.email=release@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "Initial version",
        ],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "tag", "v0.1.2"], cwd=tmp_path, check=True)
    (component / "__pycache__").mkdir()
    (component / "__pycache__/sensor.cpython-314.pyc").write_bytes(b"bytecode")
    return tmp_path


@pytest.mark.parametrize("version", ["0.1.3", "v0.1.3"])
def test_archive_contains_versioned_tracked_integration_only(
    release_repo: Path,
    version: str,
) -> None:
    assert prepare_release(release_repo, version) == "0.1.3"
    with ZipFile(release_repo / "dist/promql.zip") as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            "sensor.py",
            "translations/en.json",
        }
        assert json.loads(archive.read("manifest.json")) == {
            "domain": "promql",
            "version": "0.1.3",
        }
        assert archive.read("sensor.py") == b'"""Sensor source."""\n'
    assert subprocess.check_output(
        ["git", "tag", "--list"], cwd=release_repo, text=True
    ).splitlines() == ["v0.1.2"]


@pytest.mark.parametrize(
    "version",
    [
        "0.1.2",
        "0.1.1",
        "v0.0.9",
        "latest",
        "01.2.3",
        "1.2",
        "1.2.3-rc1",
        "0.1.3\ntag=latest",
        "$(touch injected)",
    ],
)
def test_invalid_or_reused_versions_leave_checkout_untouched(
    release_repo: Path,
    version: str,
) -> None:
    manifest_path = release_repo / "custom_components/promql/manifest.json"
    before = manifest_path.read_bytes()
    with pytest.raises(ValueError):
        prepare_release(release_repo, version)
    assert manifest_path.read_bytes() == before
    assert not (release_repo / "dist/promql.zip").exists()


def test_version_order_is_numeric(release_repo: Path) -> None:
    subprocess.run(["git", "tag", "v0.9.0"], cwd=release_repo, check=True)
    assert prepare_release(release_repo, "0.10.0") == "0.10.0"


def test_existing_release_can_rebuild_its_archive(release_repo: Path) -> None:
    assert prepare_release(release_repo, "v0.1.2", existing_release=True) == "0.1.2"
    with ZipFile(release_repo / "dist/promql.zip") as archive:
        assert json.loads(archive.read("manifest.json"))["version"] == "0.1.2"
