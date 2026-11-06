"""Keep device payloads separate from quest sources and distribution licenses."""
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[3]
SOURCES = ROOT / "tools/apps/urq/sources"
DEVICE_EXCLUSIONS = {
    'house_that_jack_built': 'literary word-substitution exercise; retained only as a regression fixture',
}


def _directory(path):
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError('unsafe URQ distribution directory: ' + str(path))


def _file(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('missing/unsafe URQ distribution file: ' + str(path))
    return path.read_bytes()


def _catalog():
    report = json.loads((ROOT / 'tools/apps/urq/catalog-report.json').read_text())
    known = {game['id'] for game in report['games']} | set(DEVICE_EXCLUSIONS)
    published = set(report['published']) - set(DEVICE_EXCLUSIONS)
    if not published <= known or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', key) for key in known):
        raise ValueError('invalid URQ distribution catalog')
    return known, published


def _device_plan():
    known, published = _catalog()
    source = ROOT / 'programs/urq'
    _directory(source)
    files = {'autoexec.wbmp': _file(source / 'autoexec.wbmp')}
    for key in sorted(published):
        folder = source / key
        _directory(folder)
        index = _file(folder / 'game.urq')
        if len(index) < 64 or index[:10] != b'MK61URQ\0\x01\0':
            raise ValueError('invalid URQ index: ' + str(folder / 'game.urq'))
        parts, = struct.unpack_from('<H', index, 40)
        if not parts:
            raise ValueError('URQ index has no data parts: ' + key)
        files[key + '/game.urq'] = index
        for name in ['autoexec.wbmp', *(f'p{number:04d}.uqd' for number in range(parts))]:
            files[key + '/' + name] = _file(folder / name)
    return files, known, published


def _device_name(name):
    return re.fullmatch(r'game\.urq|p[0-9]{4}\.uqd|autoexec\.wbmp', name, re.I) is not None


def _prune_plan(destination, expected, known, licenses=False):
    """Only reserved payload names in known catalog namespaces are owned.

    Saves, notes, custom quests and unknown directories are never traversed or
    removed. Reject symlink redirects before copying or pruning any payload.
    """
    if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', key) for key in known):
        raise ValueError('invalid URQ distribution namespace')
    for name in expected:
        parts = name.split('/')
        if '\\' in name or not (parts == ['autoexec.wbmp'] and not licenses or
                len(parts) == 2 and parts[0] in known and
                (parts[1] in ('AUTHORS.txt', 'LICENSE.txt') if licenses else _device_name(parts[1]))):
            raise ValueError('invalid URQ distribution path: ' + name)
    _directory(destination)
    removals, folders = [], []
    if not licenses:
        root_icon = destination / 'autoexec.wbmp'
        if root_icon.is_symlink() or (root_icon.exists() and not root_icon.is_file()):
            raise ValueError('unsafe URQ distribution file: ' + str(root_icon))
    stock_icon = _file(ROOT / 'doc/explorer-icons/license.wbmp') if licenses else None
    for key in sorted(known):
        folder = destination / key
        _directory(folder)
        if not folder.exists():
            continue
        folders.append(folder)
        for path in folder.iterdir():
            owned = path.name.lower() in ('authors.txt', 'license.txt', 'autoexec.wbmp') if licenses else _device_name(path.name)
            if not owned:
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError('unsafe URQ distribution file: ' + str(path))
            relative = key + '/' + path.name
            if licenses and path.name.lower() == 'autoexec.wbmp':
                # Icons for current license folders are installed by the bundle
                # packager. Only a retired, stock-generated icon can be pruned.
                if any(name.startswith(key + '/') for name in expected) or path.read_bytes() != stock_icon:
                    continue
            if relative not in expected:
                removals.append(path)
    for relative in expected:
        target = destination / relative
        _directory(target.parent)
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError('unsafe URQ distribution file: ' + str(target))
    return removals, folders


def prune_device_library(destination, expected, known):
    """Prune obsolete generated files after a successful library generation."""
    destination = Path(destination)
    removals, folders = _prune_plan(destination, set(expected), set(known))
    for path in removals:
        path.unlink()
    for folder in folders:
        if not any(folder.iterdir()):
            folder.rmdir()


def preflight_device_library(destination, known):
    """Reject redirected output namespaces before a generator writes anything."""
    _prune_plan(Path(destination), {'autoexec.wbmp'}, set(known))


def _sync(destination, files, known, licenses=False):
    destination = Path(destination)
    for source in (ROOT / 'programs/urq', SOURCES):
        if destination.resolve().is_relative_to(source.resolve()) or source.resolve().is_relative_to(destination.resolve()):
            raise ValueError('URQ distribution must not overlap its sources: ' + str(destination))
    removals, folders = _prune_plan(destination, set(files), known, licenses)
    for path in removals:
        path.unlink()
    result = []
    for relative, payload in sorted(files.items()):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        result.append(target)
    for folder in folders:
        if not any(folder.iterdir()):
            folder.rmdir()
    return result


def copy_device_library(destination):
    files, known, _ = _device_plan()
    return _sync(destination, files, known)


def copy_licenses(destination):
    _, known, published = _device_plan()
    files = {}
    _directory(SOURCES)
    for key in sorted(published):
        folder = SOURCES / key
        _directory(folder)
        for name in ("AUTHORS.txt", "LICENSE.txt"):
            files[key + '/' + name] = _file(folder / name)
    return _sync(destination, files, known, licenses=True)
