#!/usr/bin/env python3
"""Offline ownership/hash gates for the same-firmware package A/B/A fixture."""
import hashlib
from pathlib import Path
import tempfile
from unittest.mock import patch
import hil_turochamp_merge as h

OLD = '/System/VMCache/VMC-000f.app'
NEW = '/System/VMCache/VMC-0030.app'
USER = '/System/BASIC.app'
GAME = '/TCMERGE/legal.tbi'


def fingerprint(files):
    return dict(files={name: dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
                       for name, data in files.items()}, directories=[])


class Port:
    def __init__(self, files):
        self.files = files
        self.operations = []

    def command(self, command, timeout):
        assert timeout == 30 and command.startswith('rm "') and command.endswith('"')
        path = command[4:-1]
        self.operations.append(('remove', path))
        del self.files[path]
        return 'Removed 1 entry.'


def main():
    original = {OLD: b'original cache', USER: b'original APP'}
    snapshot = fingerprint(original)
    with tempfile.TemporaryDirectory(prefix='mk61-chess-merge-self-') as directory:
        backup = Path(directory)
        old = backup/OLD.lstrip('/')
        old.parent.mkdir(parents=True)
        old.write_bytes(original[OLD])
        app = backup/USER.lstrip('/')
        app.write_bytes(original[USER])

        def exercise(files, fail=False, replace_basic=False):
            port = Port(files)
            def write(port, remote, data):
                port.operations.append(('write', remote))
                port.files[remote] = data
            with patch.object(h.storage_hil, 'fingerprint', lambda port: fingerprint(port.files)), \
                 patch.object(h, 'write_file', write), \
                 patch.object(h, 'read_file', lambda port, remote: port.files[remote]):
                try:
                    removed = h.restore_vm_cache(port, snapshot, backup, replace_basic)
                except AssertionError:
                    assert fail and not port.operations
                    return port
                assert not fail
                return port, removed

        port, removed = exercise({**original, OLD: b'changed', NEW: b'new cache', GAME: b'game'})
        assert removed == [NEW] and port.files == {**original, GAME: b'game'}
        port, removed = exercise({USER: original[USER], GAME: b'game'})
        assert removed == [] and port.files == {**original, GAME: b'game'}
        for remote in ('/user.txt', '/TCMERGE-other/file.tbi', '/System/VMCache/VMC-user.app'):
            exercise({**original, NEW: b'new', remote: b'foreign'}, fail=True)
        exercise({**original, NEW: b'new', USER: b'foreign change'}, fail=True)
        port, _ = exercise({**original, USER:b'candidate'}, replace_basic=True)
        assert port.files == original and port.operations == [('write',USER)]
        app.write_bytes(b'corrupt APP backup')
        exercise({**original, NEW:b'new', USER:b'candidate'}, fail=True, replace_basic=True)
        old.write_bytes(b'corrupt backup')
        exercise({**original, OLD: b'changed', NEW: b'new'}, fail=True)
    print('Turochamp merge HIL: owned paths, original hashes and pre-mutation rejection PASS')


if __name__ == '__main__':
    main()
