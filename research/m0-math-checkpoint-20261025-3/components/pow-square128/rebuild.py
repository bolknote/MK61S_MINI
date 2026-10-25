"""Rebuild actual qualified inputs at their original private paths, byte exact."""
from pathlib import Path
import hashlib, json, subprocess, sys
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
assert not (W / 'FROZEN.json').exists()
commands = [c for name in ['build.json', 'unit-build.json']
            for c in json.loads((W / name).read_bytes())['commands']]
outputs = {Path(c[c.index('-o') + 1]) for c in commands}
assert len(outputs) == len(commands) == 13
before = {str(p): p.read_bytes() for p in outputs}
for command in commands:
    subprocess.run(command, cwd=W, check=True)
for p, data in before.items():
    assert Path(p).read_bytes() == data, p
out = dict(status='PASS_THIRTEEN_FULL_SOURCE_OBJECT_AND_ELF_REBUILDS_BYTE_EXACT',
           outputs={p: hashlib.sha256(data).hexdigest() for p, data in before.items()},
           commands=commands, actual_ARM_or_MPFR_calls=0, hardware_accessed=False)
(W / 'rebuild-proof.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps({k:v for k,v in out.items() if k != 'commands'}, indent=2))
