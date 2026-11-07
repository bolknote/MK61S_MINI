#!/usr/bin/env python3
"""Historical verification must never relabel changed code as measured code."""
import gzip,hashlib,importlib.util,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    spec=importlib.util.spec_from_file_location('old_strchr_evidence',ROOT/'research/strchr-2026-10-28/verify_m0_evidence.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='strchr-historical-HOST-') as folder:
        root=Path(folder);module.ROOT=root;module.E=root/'evidence';module.E.mkdir()
        measured=b'measured code\n';ref=dict(path='old.c',bytes=len(measured),sha256=hashlib.sha256(measured).hexdigest())
        (root/'old.c').write_bytes(measured);assert module.source_bytes(ref)==(measured,False)
        (root/'old.c').write_bytes(b'new unmeasured surrounding source\n')
        try:module.source_bytes(ref)
        except AssertionError:pass
        else:raise AssertionError('Changed current source accepted as historical')
        source=module.E/'source/old.c.gz';source.parent.mkdir();source.write_bytes(gzip.compress(measured,mtime=0));assert module.source_bytes(ref)==(measured,True)
        source.write_bytes(gzip.compress(b'wrong historical code',mtime=0))
        try:module.source_bytes(ref)
        except AssertionError:pass
        else:raise AssertionError('Corrupted historical source accepted')
    print('current identity, immutable historical fallback and missing/corrupt source rejection PASS')
if __name__=='__main__':main()
