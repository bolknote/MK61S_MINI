"""Regress the combined AI/Spectrum firmware which built but could not start."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.firmware.picocalc.build_picocalc import audio_memory_budget

# Physical failure: BUILD7A1635FF, full native/shared runtime,99152-byte heap.
try:
    audio_memory_budget(130224, True)
except ValueError as error:
    assert '99152' in str(error) and '108544' in str(error)
else:
    raise AssertionError('firmware which cannot start Spectrum was accepted')
assert audio_memory_budget(120000,True)['heap_capacity_bytes']==109376
assert audio_memory_budget(130224,False)['minimum_heap_bytes'] is None
print('Combined AI/Spectrum firmware SRAM regression rejected before packaging: PASS')
