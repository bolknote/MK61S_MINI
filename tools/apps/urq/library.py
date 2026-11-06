"""Keep device payloads separate from quest sources and distribution licenses."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[3]
SOURCES = ROOT / "tools/apps/urq/sources"
DEVICE_SUFFIXES = {".urq", ".uqd", ".wbmp"}
DEVICE_EXCLUSIONS = {
    'house_that_jack_built': 'literary word-substitution exercise; retained only as a regression fixture',
}


def copy_device_library(destination):
    destination = Path(destination)
    source = ROOT / "programs/urq"
    result = []
    for path in sorted(source.rglob("*")):
        if path.relative_to(source).parts[0] in DEVICE_EXCLUSIONS:
            continue
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
        if folder.name in DEVICE_EXCLUSIONS:
            continue
        if not (ROOT / 'programs/urq' / folder.name / 'game.urq').is_file():
            continue
        for name in ("AUTHORS.txt", "LICENSE.txt"):
            target = destination / folder.name / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(folder / name, target)
            result.append(target)
    return result
