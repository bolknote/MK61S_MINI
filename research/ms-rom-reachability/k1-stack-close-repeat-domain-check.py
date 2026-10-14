#!/usr/bin/env python3
"""Conditional class incompatibility, not global impossibility of K1.

The first successful closed path moves old P7 into Q. Its LastX reserve
uses a class-7 P7 formatter. A later repeat's first visible rotation
formats that same word with Z/U markers instead. Native scheduling and
the prefix reaching these local premises must be checked separately.
"""
import runpy
from pathlib import Path

root=Path(__file__).resolve().parent
f=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']

if __name__=='__main__':
    runpy.run_path(str(root/'k1-u-reserve-control-mask-check.py'))['producer'](
      'U',0x25,('T','U'),'X','V','control')
    runpy.run_path(str(root/'k1-upper-replay-map-check.py'))['rotation'](
      'marker',('T','U'),[('X','Y'),('Y','Z'),('Z','T'),('T','X')],['control','control'])
    # Accepted class in the already verified LastX reserve: old upper a
    # is copied to W, preserving the newly read v in X.
    f(9,7,source_slot='P7',marker_slots=('marker','T','V'),
      target_by_class=['X']*7+['W']*2)
    # Same actual a, now Q after the complete first call, is read from X
    # before the next secondary rotation. After the rotation Z/U remain.
    targets=['V']*5+['Q']*2+['X']*2
    f(9,7,source_slot='X',marker_slots=('marker','Z','U'),target_by_class=targets)
    # Compare the long q used by the successful first call.
    f(9,0,source_slot='X',marker_slots=('marker','Z','U'),target_by_class=targets)
    print('PASS local conflict: class-7 P7 -> W in LastX, but the same class-7 word -> X in the repeated first rotation.',flush=True)
    print('LIMIT: conditional formatter contracts only. This does not rule out a different entry, an adapter, other timing, or full K1.',flush=True)
