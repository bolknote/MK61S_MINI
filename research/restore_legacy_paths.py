"""Restore ignored legacy tmp paths for unchanged archived research scripts."""
from pathlib import Path
import os

research = Path(__file__).resolve().parent
scratch = research.parent / 'tmp'
scratch.mkdir(exist_ok=True)
for source in sorted(research.iterdir()):
    if not source.is_dir():
        continue
    target = scratch / source.name
    if target.is_symlink() and target.resolve() == source.resolve():
        continue
    if target.exists() or target.is_symlink():
        raise SystemExit(f'Refusing to replace an existing workspace: {target}')
    target.symlink_to(os.path.relpath(source, scratch), target_is_directory=True)
    print(target.relative_to(research.parent))
