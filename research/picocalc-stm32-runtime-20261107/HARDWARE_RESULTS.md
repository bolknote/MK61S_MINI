# STM32 Southbridge runtime: physical results, 2026-11-07

The Southbridge runtime is **installed and running** on the PicoCalc STM32.
The earlier `southbridge/README.md` is the frozen pre-flash design/build note;
this file and `STATUS.json` record the subsequent deployment and measurements.

ROM ID was 0x0410, loader version0x22. The exact25,824-byte image SHA256 is
`f16f54f8eec954966a6a810be583a0dd61fb9cd16fb0a461529552dcf12b2069`.
It was written with read-back verification to the first26 1-KiB pages only.
No GO/reset, protection, option-byte or old-firmware backup command was used.
The user returned DIP1 OFF and power-cycled the board afterward.

The initial programmer command combined mutually exclusive `-S` and `-e`;
the utility rejected it before opening the serial port. The executed command
used `-s0 -e26` for the same bounded address range. The final pre-flash review
packet SHA256 is
`6b98cc802b83daf6467c0ab05f5089aac49cd6d6bf58d95153a81e18b0fb84c8`.

## Actual native module operation

A separate native Pico APP claimed UART1 GP8 TX / GP9 RX, uploaded a328-byte
Q4 × INT16 module over the real wire, ran four jobs and checked64 rows against
an independent int64 reference. Replaying START did not execute the job twice.
UNLOAD and a subsequent HELLO confirmed an empty slot. UART line errors were0.
The adapter restores the pin mux/pads/reset/UART configuration on exit;
the same restoration paths also passed an executable M0 MMIO-model test.

The complete diagnostic took53,385µs over33 requests; its maximum RTT was2,126µs.
These figures include formatting, polling and deliberate scheduling delays.
The configured STM32 UART rate is2,250,000baud. At Pico PERI48MHz the divisor
IBRD1/FBRD21 gives2,258,823baud (+0.39%). The tested exchange had no line errors.

Pico itself stayed at125MHz with its original F0E86C32/5009F89E firmware.
The native APP was4,273 bytes on SD and6,456 bytes loaded, including BSS.
No resident Pico image or M0 fixture was written.

## DWT kernel measurements at72MHz

A second1,244-byte native module uses1,164 bytes for code/data+BSS. It measures
three32-MAC kernels from SRAM with DWT CYCCNT, preserving CTRL/DEMCR at unload.
Each kernel had1,024 measured calls over64 independently checked input rows.
Separate ARM execution covered136 additional random/extreme int64-reference
rows, full512-byte READs, relocation, counter absence and DWT state restoration.

| Kernel | Minimum cycles per32 MAC | Mean cycles | Minimum cycles/MAC |
|---|---:|---:|---:|
| Word-load loop |531|533.42|16.59|
| Unrolled UBFX |302|303.27|9.44|
| XOR8 + unrolled SBFX |273–274|274.65|8.53–8.56|

The best kernel is about1.94× faster than the loop and1.10× faster than the
unrolled UBFX variant. This comparison includes unrolling and extraction;
it is not an isolated latency test of one instruction or a whole-model speedup.
The sampled bracket overhead was1 cycle. Raw counts retain function-call and
load costs; interrupt outliers are visible in the per-job maxima.

Weights retain the original offset-Q4 format `nibble-8`. XOR0x88888888 converts
eight packed nibbles to signed two's-complement fields before SBFX. Every
checked result matched; no activation/weight precision change was introduced.
CLZ and RBIT were not benchmarked here.

DWT/µs clock checks gave approximately72 cycles perµs in all four jobs.
The longest cooperative call observed was331µs. Frequencies above72MHz were
not enabled or measured.

## Job/READ transport capacity

The module also generated64 deterministic512-byte blocks, completed during
INIT. Pico read each block in252+252+8-byte chunks and checked all32,768 bytes.
The block loop, including WRITE/START/READ framing and keyboard polling, took
379,291µs: **86,393 payload bytes/s**, or84.37KiB/s. UART errors were0.

This is a blocking, stop-and-wait native APP measurement, not the physical line
limit. It does not include AY synthesis or concurrent Spectrum/LCD work and
does not prove that100KB/s stereo audio is sustainable. The nominal50KB/s
mono16/25kHz payload is below this measured transport rate; actual renderer
headroom requires its own test. An async/DMA Pico audio backend is separate work.

## Startup and cleanup

The first post-power-cycle status had135 cumulative I2C aborts, one QPI fallback
and SD not mounted. Repeated C5 samples showed no further counter growth.
A read-only `df` retried the mount successfully; no reset or formatting was
needed. Keyboard I2C remained online. Both physical probes finished with the
same counters, no new CRC/DMA/LCD/SD failures, CLOSED/NONE and APP buffers0.
Full cold-boot sequencing and physical key-matrix coverage were not exercised.

Only the newly created `/S3UART7` and `/S3BEN7` scratch directories were used;
both were removed after the probes. CDC was closed and the shared lease
released. Calculator values, RTC, settings and old firmware were not saved or
restored. The installed Pico firmware and its clock were unchanged.

## Artifacts and reusable source

All output paths below are under `.build/stm32-module-runtime-20261107/southbridge-runtime/`:

- `write-verify.json` and `write-verify.log`: actual STM32 programming receipt.
- `pico-probe/hardware-result.json`: real load/run/replay/unload receipt.
- `module-bench/`: native module, disassembly and independent ARM verification.
- `pico-bench/hardware-result.json`: raw DWT and transport records plus cleanup.
- `hardware-summary.json`: parsed means, rates and clock checks.
- `STM32-RUNTIME-HANDOFF.json`: released hardware window and pinned receipts.

The reusable portable C client is `pico/stm3_client.h/.c`; the RP2040-only
polling adapter is `pico/pico_uart1.h/.c`. Their blocking interface is intended
for diagnostics and small request/response work. The audio agent owns its
asynchronous transport/backend implementation. `tools/build_m3_bench.py`,
`tools/build_pico_probe.py --bench` and `tools/run_pico_probe.py --bench`
reproduce the separate module build, APP build and finite hardware run.
