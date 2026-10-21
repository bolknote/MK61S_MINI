#!/usr/bin/env python3
"""Export the selected GAS candidate as a self-contained production C include.

The resulting function must be byte-identical to own64; code-proof.json checks
that against the tested ELF, standalone APP and complete firmware builds.
"""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
source=(HERE/'candidates.S').read_text()
parts={
    'm0':source.split('#if defined(__ARM_ARCH_6M__)\n',1)[1].split('#else\n.cpu cortex-m4',1)[0],
    'm4':source.split('#else\n.cpu cortex-m4',1)[1].split('#endif\nmove own16',1)[0],
}
for cpu,part in parts.items():
    part=part.replace('function \\name\n','').replace('end \\name\n','').replace('.L','.Lmk61_memmove_')
    part=' .syntax unified\n'+part+'\nmove body,1\n.purgem move\n.purgem directional\n'+('.purgem merge\n' if cpu=='m0' else '.purgem block\n')
    import re
    for name in ('move','directional','merge','block'):
        part=re.sub(r'\b'+name+r'\b','mk61_move_'+name,part)
    comment='''/* Directional, bounded memmove. Preserve every unread source byte.
 * Source and destination may overlap by any number of bytes.
 * Exported by research/memmove-2026-10-21/export.py from the measured candidate.
 * M0+: aligned LDM/STM, bounded shift/merge for unequal alignment.
 * M4: aligned LDM/LDMDB, ordinary stores, exact prefix and tail accesses. */
'''
    (ROOT/f'code/memmove_{cpu}.inc').write_text(comment+''.join(json.dumps(line+'\n')+'\n' for line in part.splitlines()))
