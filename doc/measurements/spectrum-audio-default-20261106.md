# Automatic Spectrum audio clock, 2026-11-06

Historical record of the initial clock/media work. The later hardware tests,
including Ianna's original menu and controls, are recorded in
[the final hardware report](spectrum-hardware-20261106.md).

Ordinary firmware BUILD `55C15128`, CRC `D895F27B`, 1537024 bytes.
Source and raw HOST/device records:
`.build/spectrum-audio-default-200-20261106/qualification.json`.
The firmware includes the current AI V3 runtime and its two LCD/result fixes.

The Sword of Ianna starts from the installed `IANNA.Z80` snapshot, with AY
and the exact weighted mixer. The on-device sequence was 125 → 200 → 125
on pause → 200 on resume; BOOTS stayed 29. USB/peripheral stayed 48 MHz,
PSRAM SCK 16.667 MHz, PCM 25 kHz and PWM input 100 MHz. The game was left
running for the user, all CDC descriptors closed. A subsequent accidental
exit was recovered and the game was again verified running at 200 MHz.
This is a launch/lifecycle check, not a new physical FPS or speaker-latency measurement.

An initial combined image, `7A1635FF`, built but failed Spectrum's runtime
SRAM allocation. Its 99152-byte heap was insufficient; the original HOLD
and serial output are retained. The final image has 117312 static SRAM
bytes and a 112064-byte heap. The VM dispatcher executes from XIP with
its existing O2 code; the fused integer loop stays in SRAM. VM throughput
after that placement change has not been measured.

Packaging now requires at least 108544 heap bytes for automatic audio:
48 KiB APP, 30 KiB fixed banks, 16 KiB page cache, 4 KiB service allocations
and 8 KiB reserve. A regression check rejects the actual failed image's
layout. Clock/audio/power and native integration tests passed with
ASan/UBSan; exact AY output/state comparisons cover 817792 samples.

The old AI 300 MHz transition crash (`F64DE93C`) remains retained and was
matched against its released diagnostic record; it was not cleared.
No old Flash backup, calculator-state or RTC capture/restore was performed.

The initial Ianna snapshot selects keyboard controls: O/P left/right, Q/A up/down,
Space fire/action, Caps Shift select (PicoCalc Ctrl). Esc pauses to the
emulator OSD; Resume returns to emulation. A second Esc at the root OSD exits.

An earlier controller switched the installed checkpoint to Kempston by
changing one literal file byte at offset62309 from3 to0
(bank5, guest address0x672B); the original checkpoint remains archived.
Readback SHA-256 is
`14ee17e897cd3c75870b0664dfd82abe3a50016235441db9b5093a7d81b2a350`.
HOST idle/right controls differ in zero bitmap bytes in keyboard mode and
117 bytes in Kempston mode. The emulator's Options also confirms Kempston.
The game was reopened and left running at200MHz, all CDC handles closed;
no Flash writes. Records: `.build/spectrum-audio-default-200-20261106/kempston/`.

## Original media restored; disk startup remains unresolved

The user rejected that checkpoint modification. The original `IANNA.Z80`
was restored and read back byte-for-byte, SHA-256
`787853cbd8bc3924e802ded2c1f78876ecdd3629d321602a08199945890446ee`.
The separately authorized new 16 MiB `IANNA.img`, containing unmodified
game files and esxDOS, was installed, fully read back and normally ejected.
Its SHA-256 is
`bc821c16e25d82a2319f018e60ea9b6a5d654ba09993e891b2a969a00fa02f01`.
Records are in `.build/spectrum-audio-default-200-20261106/original-menu/`.
HOST boot from that image reaches the original menu; its normal F5 fire
input selects Kempston. The on-device menu selection is still pending.

The first hardware disk boot lost USB on entry to emulation and did not
reenumerate within the controller's 20 s bound (`BOOT.result`, HOLD).
Power was then cycled by the user, so no retained fault record from that
incident survived. Its cause has not been established.

After power-on, PSRAM passed the boot test in SPI fallback mode rather
than QPI. A native `fsget IANNA.Z80` at125MHz exceeded its 15 s host bound
before emitting the GET header (`CLOCK-NO-DISK.result`, HOLD). This was
not a second proven board hang: the subsequent Math admission record
observed the same USB session, BOOTS1 and CRASH=NONE, with forward
progress to18496432 PSRAM read bytes and34499 sector-cache hits. The
previous Spectrum status had4696 PSRAM read bytes and no such cache
activity. `fsget` reopens/seeks the file for every96-byte chunk in both
passes; slow SPI cache traffic is a concrete performance suspect, not a
proven explanation of the first USB loss.

`READ-STALL-PROBE` did not open CDC: its nonblocking advisory lock failed
while Math was flashing BASE. That failure must not be counted as an
unresponsive device. The user subsequently requested offline work while
Math retains the hardware window. Earlier checkpoint lifecycle PASSes
do not qualify this new disk boot or the currently installed Math image.
