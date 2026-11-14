"""Flash belongs to firmware up to the two persistent settings sectors."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.firmware.picocalc.build_picocalc import FIRMWARE_FLASH_LIMIT, firmware_flash_budget

assert FIRMWARE_FLASH_LIMIT == 0x1FE000
for size in (1,1786868,1836020,0x1C0000,0x1C0001,FIRMWARE_FLASH_LIMIT):
    firmware_flash_budget(size)
for size in (FIRMWARE_FLASH_LIMIT+1,2*1024*1024,0):
    try:firmware_flash_budget(size)
    except ValueError as error:assert 'settings' in str(error)
    else:raise AssertionError(f'overlapping image accepted: {size}')
print('Firmware/settings boundary: no emulator ROM reservation; settings overlap rejected PASS')
