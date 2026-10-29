#!/usr/bin/env python3
"""LPM workflow adapter for the native meshtasticd Debian runtime package."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "tools" / "meshtasticd-aarch64.Dockerfile"


def run(arguments: list[str], *, cwd: Path = ROOT) -> None:
    subprocess.run(arguments, cwd=cwd, check=True)


def write_report(path: Path, cases: list[tuple[str, str | None]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element("testsuite", name="meshtasticd-lpm", tests=str(len(cases)))
    for name, failure in cases:
        case = ET.SubElement(suite, "testcase", name=name)
        if failure:
            ET.SubElement(case, "failure", message=failure)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def test(report: Path) -> None:
    cases: list[tuple[str, str | None]] = []
    required = (
        ROOT / "platformio.ini",
        ROOT / "variants/native/portduino/platformio.ini",
        ROOT / "debian/control",
        ROOT / "debian/rules",
        ROOT / "debian/meshtasticd.install",
        DOCKERFILE,
    )
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    cases.append(("firmware-package-inputs", ", ".join(missing) if missing else None))

    rules = (ROOT / "debian/rules").read_text(encoding="utf-8")
    install = (ROOT / "debian/meshtasticd.install").read_text(encoding="utf-8")
    package_error = None
    if "platformio run -e native-tft" not in rules:
        package_error = "debian/rules does not build native-tft"
    elif ".pio/build/native-tft/meshtasticd" not in install:
        package_error = "Debian install rules do not install native-tft meshtasticd"
    cases.append(("native-tft-package-definition", package_error))

    try:
        subprocess.run(["docker", "buildx", "version"], check=True, stdout=subprocess.DEVNULL)
        docker_error = None
    except (OSError, subprocess.CalledProcessError) as exc:
        docker_error = f"docker buildx unavailable: {exc}"
    cases.append(("docker-buildx", docker_error))

    write_report(report, cases)
    if any(failure for _, failure in cases):
        raise SystemExit(1)


def package(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    if not DOCKERFILE.is_file():
        raise SystemExit(f"missing builder: {DOCKERFILE}")

    try:
        source_revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        source_revision = "unknown"

    package_version = os.environ.get("MESHTASTICD_DEB_VERSION")
    if not package_version:
        package_version = subprocess.check_output(
            [sys.executable, "bin/buildinfo.py", "deb"], cwd=ROOT, text=True
        ).strip()

    with tempfile.TemporaryDirectory(prefix="meshtasticd-lpm-") as temporary:
        artifact_dir = Path(temporary) / "artifacts"
        run(
            [
                "docker",
                "buildx",
                "build",
                "--platform",
                "linux/arm64",
                "--progress=plain",
                "--target",
                "artifact",
                "--build-arg",
                f"PKG_VERSION={package_version}",
                "--build-arg",
                f"SOURCE_REV={source_revision}",
                "--output",
                f"type=local,dest={artifact_dir}",
                "-f",
                str(DOCKERFILE),
                ".",
            ]
        )
        packages = sorted(artifact_dir.glob("*.deb"))
        if not packages:
            raise SystemExit("Docker build completed without producing a Debian package")
        for artifact in packages:
            shutil.copy2(artifact, output / artifact.name)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)

    test_parser = subparsers.add_parser("test")
    test_parser.add_argument("--report", type=Path, required=True)

    pack_parser = subparsers.add_parser("pack")
    pack_parser.add_argument("--output-dir", type=Path, required=True)

    args = parser.parse_args()
    if args.action == "test":
        test(args.report.resolve())
    else:
        package(args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
