"""Keep device payloads separate from quest sources and distribution licenses."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[3]
SOURCES = ROOT / "tools/apps/urq/sources"
DEVICE_SUFFIXES = {".urq", ".uqd", ".wbmp"}


def copy_device_library(destination):
    destination = Path(destination)
    source = ROOT / "programs/urq"
    result = []
    for path in sorted(source.rglob("*")):
        if path.is_file() and path.suffix in DEVICE_SUFFIXES:
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            result.append(target)
    return result


def copy_licenses(destination):
    destination = Path(destination)
    result = []
    for folder in sorted(SOURCES.iterdir()):
        if not folder.is_dir():
            continue
        for name in ("AUTHORS.txt", "LICENSE.txt"):
            target = destination / folder.name / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(folder / name, target)
            result.append(target)
    return result
