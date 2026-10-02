"""Prepare a versioned HACS archive without publishing or changing Git refs."""

import argparse
import json
import re
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

_VERSION = re.compile(r"v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_COMPONENT = Path("custom_components/promql")


def prepare_release(
    root: Path, requested_version: str, *, existing_release: bool = False
) -> str:
    """Validate the version, update the manifest, and zip tracked component files."""
    match = _VERSION.fullmatch(requested_version.strip())
    if match is None:
        raise ValueError("Use a stable version such as 0.1.3 or v0.1.3.")
    version = ".".join(match.groups())
    version_parts = tuple(map(int, match.groups()))

    if not existing_release:
        tags = subprocess.check_output(
            ["git", "tag", "--list"], cwd=root, text=True
        ).splitlines()
        for tag in tags:
            if (tag_match := _VERSION.fullmatch(tag)) is not None:
                if version_parts <= tuple(map(int, tag_match.groups())):
                    raise ValueError(f"Choose a version newer than existing tag {tag}.")

    manifest_path = root / _COMPONENT / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["version"] = version
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    # Tests create bytecode caches; only tracked integration assets belong in HACS.
    tracked_paths = (
        subprocess.check_output(
            ["git", "ls-files", "-z", "--", str(_COMPONENT)], cwd=root
        )
        .decode()
        .split("\0")
    )
    archive_path = root / "dist/promql.zip"
    archive_path.parent.mkdir(exist_ok=True)
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
        for path in filter(None, tracked_paths):
            relative_path = Path(path)
            archive.write(root / relative_path, relative_path.relative_to(_COMPONENT))

    return version


def main() -> None:
    """Prepare the current checkout and emit GitHub Actions output values."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument(
        "--existing-release",
        action="store_true",
        help="Build an archive for an already published release tag.",
    )
    args = parser.parse_args()
    try:
        version = prepare_release(
            Path.cwd(), args.version, existing_release=args.existing_release
        )
    except ValueError as error:
        parser.error(str(error))
    print(f"version={version}\ntag=v{version}")


if __name__ == "__main__":
    main()
