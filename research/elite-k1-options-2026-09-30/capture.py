"""Capture the unmodified ELITE test corpus with the current real core."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path('/Users/bolk/Projects/MK61S_MINI')
HERE=Path(__file__).resolve().parent
sys.argv=[str(ROOT/'tests/elite_game_test.py'),str(HERE/'runner')]
spec=importlib.util.spec_from_file_location('game_tests',ROOT/'tests/elite_game_test.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
original=m.play
sessions=[]
def play(commands):
    states=original(commands)
    sessions.append(dict(commands=commands,states=states))
    return states
m.play=play
m.main()
(HERE/'baseline.json').write_text(json.dumps(dict(labels=m.LABELS,sessions=sessions)))
print('CAPTURE',len(sessions),sum(len(s['states']) for s in sessions),
      sum(t['steps'] for s in sessions for t in s['states']),flush=True)
