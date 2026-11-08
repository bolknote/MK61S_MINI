# Classic: inline CPU frequency and CRC investigation, 2026-11-08

Working image CFD23EE8 displays «Частота CPU 96 МГц» directly in Settings. Left/right/OK change the selected profile in the list; there is no frequency submenu. Graphical Classic uses the full label;16-column displays use «CPU96МГц» with spaces in the actual formatted label. Selection takes effect after restart, as before.

Size402300 bytes versus402432 bytes for F406C241 (−132 bytes); static RAM unchanged21848 bytes. Flash headroom121988 bytes ≥16384; maximum static frame1928 bytes ≤5120. No memory or latency budget relaxed. Sealed ELF/BIN match, full internalFlash readback and runningCRC verified on first installation. Actual192×64 screen captured in compute-clock-menu-inline-20261108.png.

## CRC evidence

The short40-stack-output script passed96/144/96MHz, with noncePONG checks. ExactGAPTEST144 reproduced multiple failures. A frozen device-side ring records the complete encoded packet before Serial.write. Device sequence106:

```
device: 4d530222006a00040005008aebc58f
host:   4d530222006a00040005008eebc58f
```

DeviceCRC is valid; hostCRC is not. Byte11 changed0x8A→0x8E (XOR0x04), with length/header/remaining bytes identical. Earlier capture also found a RECT message type0x21→0x25. This specific failure is **after packet encoding**, not text interleaving inside COBS. It does not establish whether the CDC/USB driver, memory/transmission path, or unsupported overclock is responsible.

Heavy device-side validation checked2613 encoded packets and found no encoding errors, encoded-buffer mutations or queue-copy mismatches; those instrumented144MHz runs passed. A lighter packet ring still reproduced the failure and supplied the matched packet above. Additional FIFO-word tracing changed timing/layout and the test passed, so it did not supply a failing FIFO-word comparison. A minimal DSB after each FIFO write still failed144MHz and was discarded. No speculative barrier, telemetry or capture buffers are included in the working menu image.

144MHz remains unaccepted. The CPU datasheet limit is100MHz; tested144MHz is an overclock. Final requested operating profile is96MHz. Raw attempts and sealed images are retained under .build/compute-clock-20261107/menu-inline; host protocol and compute/settings tests pass. This report records a localization, **not a completed CRC fix**.

Final acceptance: actual Settings screen changed96→108→96 in the same list and returned to the exact original frame. WorkingCFD23EE8 left at96MHz; final CPU checksum3289793925 and CHIP8 59.8957FPS pass. After another reboot, firmwareCRC valid/CRASH none/MPU layoutok. CDC closed; Classic released. Nothing committed.

Продолжение завершено: [причинное разделение USB и разгона](compute-clock-crc-isolation-20261108.md). Отказ 144 МГц воспроизведён без USB и с полностью замаскированными IRQ; исправление только CDC этот режим не квалифицирует.
