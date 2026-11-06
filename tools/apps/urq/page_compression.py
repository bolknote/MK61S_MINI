"""Optional host C optimizer; the device retains its existing 512-byte decoder."""
import hashlib
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def optimal_pages(payload):
    compiler = next((shutil.which(name) for name in ('cc', 'clang', 'gcc') if shutil.which(name)), None)
    if not compiler:
        raise ValueError('optimal ZX0 needs a host C compiler; use --zx0-parser greedy without one')
    vendor = ROOT / 'tools/apps/packer/third_party/zx0'
    sources = [Path(__file__).with_name('zx0_pages.c'),
               *(vendor / name for name in ('optimize.c', 'compress.c', 'memory.c'))]
    signature = hashlib.sha256((platform.system() + platform.machine()).encode())
    for path in [*sources, vendor / 'zx0.h']:
        signature.update(path.read_bytes())
    cache = Path(tempfile.gettempdir()) / 'mk61-urq-zx0'
    cache.mkdir(exist_ok=True)
    executable = cache / ('pages-' + signature.hexdigest()[:20])
    with tempfile.TemporaryDirectory(prefix='build-', dir=cache) as temporary:
        work = Path(temporary)
        if not executable.exists():
            candidate = work / 'pages'
            process = subprocess.run([compiler, '-std=c99', '-O2', *(str(p) for p in sources),
                                      '-o', str(candidate)], capture_output=True, text=True)
            if process.returncode:
                raise ValueError('cannot build optimal ZX0: ' + process.stderr)
            candidate.replace(executable)
        (work / 'input').write_bytes(payload)
        process = subprocess.run([str(executable), str(work / 'input'), str(work / 'output')],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if process.returncode:
            raise ValueError('optimal ZX0 failed: ' + process.stderr)
        data = (work / 'output').read_bytes()
    pages, offset = [], 0
    for at in range(0, len(payload), 512):
        if offset + 2 > len(data):
            raise ValueError('truncated optimal ZX0 result')
        size, = struct.unpack_from('<H', data, offset)
        offset += 2
        if not 0 < size <= min(512, len(payload) - at) or offset + size > len(data):
            raise ValueError('invalid optimal ZX0 page')
        pages.append(data[offset:offset + size])
        offset += size
    if offset != len(data):
        raise ValueError('trailing optimal ZX0 result')
    return pages
