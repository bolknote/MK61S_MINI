"""Independently rebuild both source objects and the complete ln fixture."""
from pathlib import Path
import hashlib
import json
import subprocess

W = Path(__file__).resolve().parent
R = W / 'public-rebuild'
R.mkdir(exist_ok=False)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


b = json.loads((W/'candidate-build.json').read_text())
assert len(b['commands']) == 3
commands = []
for index, name in [(0, 'candidate-full.o'), (1, 'candidate-ratio.o')]:
    cmd = list(b['commands'][index])
    cmd[cmd.index('-o')+1] = str(R/name)
    subprocess.run(cmd, check=True)
    assert sha(R/name) == sha(W/name)
    commands.append(cmd)
link = list(b['commands'][2])
for name in ('candidate-full.o', 'candidate-ratio.o', 'candidate.elf'):
    link[link.index(str(W/name))] = str(R/name)
subprocess.run(link, check=True)
assert sha(R/'candidate.elf') == sha(W/'candidate.elf') == b['ELF_sha256']
commands.append(link)
out = dict(status='PASS_WHOLE_PUBLIC_LN_COMPONENT_REBUILDS_BYTE_EXACTLY',
           full_CPP_object_byte_exact=True, ratio_assembly_object_byte_exact=True,
           entire_ELF_byte_exact_without_exclusions=True,
           candidate_ELF_sha256=sha(W/'candidate.elf'), full_object_sha256=sha(W/'candidate-full.o'),
           source_sha256=sha(W/'native_eabi_m0_log70.inc'), commands=commands,
           hardware_accessed=False, canonical_or_frozen_changed=False,
           scope='Independent producer invocation, not independent review or production firmware.')
(W/'public-body-proof.json').write_text(json.dumps(out, indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k != 'commands'}, indent=2))
