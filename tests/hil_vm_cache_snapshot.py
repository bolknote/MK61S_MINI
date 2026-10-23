"""Conservative byte-exact HIL cleanup of legacy and paged VM caches.

Unknown paths or malformed ownership markers stop cleanup before mutation.
Readers/writers/commands are injected so the complete plan is host-testable.
"""
import hashlib
import re
import struct
import zlib

PAGES = '/System/VMCache/Pages'
LEGACY = re.compile(r'/System/VMCache/VMC-[0-9A-F]{4}\.app', re.I)
SPACES = {'indexa', 'indexb', 'image0', 'image1', 'boundaries'}


def cache_file(path):
    return bool(LEGACY.fullmatch(path)) or path.casefold().startswith(PAGES.casefold() + '/')


def cache_directory(path):
    return path.casefold() == PAGES.casefold() or path.casefold().startswith(PAGES.casefold() + '/')


def _crc(data, at):
    return zlib.crc32(data[:at]) == struct.unpack_from('<I', data, at)[0]


def validate_cache(files, directories):
    """Mirror Store::owned_cache plus its CRC-protected source markers."""
    groups = {}
    for path in directories:
        assert cache_directory(path), ('unknown cache directory', path)
        tail = path[len(PAGES):].strip('/').split('/')
        if tail == ['']:
            continue
        assert re.fullmatch(r'[0-9A-F]{4}', tail[0], re.I), ('unknown cache directory', path)
        assert len(tail) == 1 or (len(tail) == 2 and tail[1].casefold() in SPACES), ('unknown cache directory', path)
        groups.setdefault(tail[0].upper(), {})
    for path, data in files.items():
        if LEGACY.fullmatch(path):
            assert len(data) >= 64 and data[:8] == b'MK61APP\0' and struct.unpack_from('<HH', data, 8) == (1, 64) and _crc(data, 60), ('unidentified legacy cache', path)
            size = struct.unpack_from('<I', data, 24)[0]
            assert size == len(data)-64 and zlib.crc32(data[64:]) == struct.unpack_from('<I', data, 48)[0], ('legacy payload CRC', path)
            continue
        assert path.casefold().startswith(PAGES.casefold() + '/'), ('unknown cache file', path)
        tail = path[len(PAGES)+1:].split('/')
        assert re.fullmatch(r'[0-9A-F]{4}', tail[0], re.I), ('unknown cache file', path)
        root = groups.setdefault(tail[0].upper(), {})
        if len(tail) == 2 and tail[1].casefold() in ('owner.bin', 'manifest.bin'):
            root[tail[1].casefold()] = data
        else:
            assert len(tail) == 3 and tail[1].casefold() in SPACES and re.fullmatch(r'[0-9A-F]{8}\.bin', tail[2], re.I) and len(data) == 1024, ('unknown cache page', path)
    for name, markers in groups.items():
        assert markers, ('unidentified cache owner', name)
        source = int(name, 16)
        owner = markers.get('owner.bin')
        if owner is not None:
            assert len(owner) == 16 and owner[:4] == b'LFW1' and _crc(owner, 12) and struct.unpack_from('<H', owner, 4)[0] == source, ('invalid cache owner', name)
        manifest = markers.get('manifest.bin')
        if manifest is not None:
            assert len(manifest) == 64 and manifest[:4] == b'LFP1' and manifest[4] in (0, 1) and manifest[5] == 14 and _crc(manifest, 60) and struct.unpack_from('<H', manifest, 6)[0] == source, ('invalid cache manifest', name)
            assert manifest[16:20] == b'LBV2' and manifest[20] == 14 and manifest[21] in (1, 2), ('unknown cache image', name)


def cache_state(state):
    return {'files': {p: d for p, d in state['files'].items() if cache_file(p)},
            'directories': sorted(p for p in state['directories'] if cache_directory(p))}


def _outside(state, allowed_files=(), allowed_directories=()):
    return {'files': {p: d for p, d in state['files'].items() if not cache_file(p) and p not in allowed_files},
            'directories': sorted(p for p in state['directories'] if not cache_directory(p) and p not in allowed_directories)}


def _payloads(state, read):
    files = {path: read(path) for path in state['files'] if cache_file(path)}
    for path, data in files.items():
        assert state['files'][path] == {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}, ('cache snapshot changed while reading', path)
    directories = sorted(path for path in state['directories'] if cache_directory(path))
    validate_cache(files, directories)
    return files, directories


class CacheSnapshot:
    def __init__(self, state, read):
        self.state = state
        self.files, self.directories = _payloads(state, read)
        self.delta = None

    def restore(self, current, read, write, command, *, allowed_files=(), allowed_directories=()):
        # Read and validate the entire plan before the first removal/write.
        self.delta = dict(added_files=sorted(set(current['files'])-set(self.state['files'])),
                          missing_files=sorted(set(self.state['files'])-set(current['files'])),
                          changed_files=sorted(p for p in self.state['files'] if p in current['files'] and self.state['files'][p] != current['files'][p]),
                          added_directories=sorted(set(current['directories'])-set(self.state['directories'])),
                          missing_directories=sorted(set(self.state['directories'])-set(current['directories'])))
        assert _outside(current, allowed_files, allowed_directories) == _outside(self.state, allowed_files, allowed_directories), ('non-cache files or directories changed', self.delta)
        actual, directories = _payloads(current, read)
        removed = sorted(set(actual)-set(self.files))
        for path in removed:
            assert 'Removed 1 entry.' in command('rm "'+path+'"'), path
        created_dirs = sorted(set(self.directories)-set(directories), key=lambda p: (p.count('/'), p))
        for path in created_dirs:
            reply = command('mkdir "'+path+'"')
            assert 'mkdir:' not in reply, (path, reply)
        restored = []
        for path, data in self.files.items():
            if actual.get(path) != data:
                write(path, data)
                assert read(path) == data, ('cache restoration readback', path)
                restored.append(path)
        removed_dirs = sorted(set(directories)-set(self.directories), key=lambda p: (-p.count('/'), p))
        for path in removed_dirs:
            # rmdir is non-recursive: unknown/racing children remain safe.
            reply = command('rmdir "'+path+'"')
            assert 'rmdir:' not in reply, (path, reply)
        return dict(removed=len(removed), restored=len(restored), removed_files=removed, restored_files=restored,
                    removed_directories=len(removed_dirs), created_directories=len(created_dirs),
                    delta=self.delta)


def require_empty_calculator(state):
    """Cleanup may reset RAM only after the caller proves an empty calculator."""
    numbers = re.findall(r'=\s*([+\-]?\d+\.\d+)\s+([+\-]?\d+)', state['reg'] + state['stk'])
    assert len(numbers) == 20 and all(float(n) == 0 for n, e in numbers), 'cleanup requires empty calculator'
    codes = re.findall(r'\b[0-9A-F]{2}\b', state['dump'].split('\r\n', 1)[1])
    assert len(codes) == 105 and set(codes) == {'00'} and '\r\n/\r\n' in state['pwd'], 'cleanup requires empty program/root directory'
    assert re.search(r'(?m)^IP:\s*0\r?$', state['reg']) and re.search(r'(?m)^IP =\s*0\r?$', state['stk']), 'cleanup requires empty calculator/IP'
