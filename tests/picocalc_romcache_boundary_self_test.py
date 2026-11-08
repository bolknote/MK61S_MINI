"""Reject the observed firmware which overwrote the persistent ROM header."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.firmware.picocalc.build_picocalc import FIRMWARE_FLASH_LIMIT, firmware_flash_budget
from tools.apps.spectrum.spectrum_rom_cache import FLASH_OFFSET

assert FIRMWARE_FLASH_LIMIT == FLASH_OFFSET == 0x1C0000
for size in (1,1786868,FLASH_OFFSET):
    firmware_flash_budget(size)
for size in (FLASH_OFFSET+1,1836020,2*1024*1024-8192):
    try:firmware_flash_budget(size)
    except ValueError as error:assert 'ROM cache' in str(error)
    else:raise AssertionError(f'overlapping image accepted: {size}')
print('Firmware/ROMCACHE boundary: observed1836020-byte overlap rejected before packaging PASS')
