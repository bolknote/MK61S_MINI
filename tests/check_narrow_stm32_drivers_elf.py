#!/usr/bin/env python3
"""Reject a F401/F411 firmware that pulls the removed hardware adapters back in."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess

FORBIDDEN = re.compile(r"(?:\banalogRead(?:Resolution)?\b|\bSPI(?:Class|Settings)::|"
                       r"\bLiquidCrystal::|\bSTM32RTC::|\bPinMap_SPI_|\bPinMap_TIM\b|"
                       r"\b(?:Print|Stream|USBSerial)::|gpio_irq_conf|ERM19264_UC1609::CustomshiftOut|\bg_hpcd\b|\bHAL_PCD[A-Za-z_]|"
                       r"\bHAL_(?:ADC|SPI|DMA|RTC)[A-Za-z_])")

def check_symbols(text, native_panel=False):
    symbols = []
    usb_handle_size = None
    cdc_handle_size = None
    compact_layout = None
    for line in text.splitlines():
        marker = line.split()
        if len(marker) >= 3 and marker[-2:] == ["A", "mk61_usb_compact_layout"]:
            compact_layout = int(marker[0], 16)
        fields = line.split(None, 3)
        if len(fields) == 4:
            symbols.append((fields[2], fields[3]))
            if fields[3] == "hUSBD_Device_CDC": usb_handle_size = int(fields[1],16)
            if fields[3] == "_hcdc": cdc_handle_size = int(fields[1],16)
    offenders = [name for _kind, name in symbols if FORBIDDEN.search(name)]
    if native_panel:
        offenders += [name for _kind, name in symbols if
                      "ERM19264_graphics::" in name or
                      "vtable for ERM19264_UC1609" in name or
                      "ERM19264_UC1609::drawPixel" in name]
    if offenders:
        raise ValueError("removed STM32 hardware adapter remains: " + ", ".join(offenders))
    if compact_layout not in (None, 1):
        raise ValueError("unknown compact USB layout version: " + str(compact_layout))
    expected_usb, expected_cdc = (96, 28) if compact_layout == 1 else (252, 36)
    if usb_handle_size is not None and usb_handle_size != expected_usb:
        raise ValueError("USB middleware ABI is not the qualified layout: " + str(usb_handle_size))
    if cdc_handle_size is not None and cdc_handle_size != expected_cdc:
        raise ValueError("CDC control state is not the bounded ACM layout: " + str(cdc_handle_size))
    for irq in ("RTC_Alarm_IRQHandler", "RTC_WKUP_IRQHandler"):
        if not any(kind in ("T", "t") and name == irq for kind, name in symbols):
            raise ValueError("owned RTC interrupt is missing: " + irq)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf", type=Path)
    p.add_argument("--native-panel", action="store_true", help="also reject the unused UC1609 graphics base/vtable")
    args = p.parse_args()
    nm = os.environ.get("ARM_NONE_EABI_NM") or shutil.which("arm-none-eabi-nm")
    if not nm:
        for base in (Path.home()/"Library/Arduino15", Path.home()/".arduino15"):
            matches = sorted(base.glob("packages/STMicroelectronics/tools/*/*/bin/arm-none-eabi-nm"))
            if matches:
                nm = str(matches[-1]); break
    if not nm:
        p.error("arm-none-eabi-nm not found")
    try:
        result = subprocess.check_output([nm, "-S", "-C", "--defined-only", str(args.elf)], text=True)
        check_symbols(result, args.native_panel)
    except (ValueError, subprocess.CalledProcessError) as error:
        p.exit(1, str(error)+"\n")
    print("Owned STM32 drivers: no generic ADC/SPI/RTC/PWM/EXTI/PCD adapters; USB handle uses four endpoints")

if __name__ == "__main__":
    main()
