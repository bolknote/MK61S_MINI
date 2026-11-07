# STM32 native coprocessor ABI1

These are the stable production paths for the experimentally verified native
module ABI and PicoCalc UART client. Production consumers can include or compile
from `sdk/coproc` without importing a dated `research` directory. The files are
originally copied byte-for-byte from the physical module/DWT tests.
`PROVENANCE.json` records the original hashes and the subsequently added
optional START_RESULT completion command. The module ABI is unchanged.

| File | Purpose |
|---|---|
| `stm3_module.h` | Module header, target, limits and native entry/API types |
| `module.ld` | Flat Cortex-M3 link image, absolute relocations, 6KiB limit |
| `elf32.py` | Standard-library-only reader for trusted build-produced ARM ELFs |
| `pico_uart1.h/.c` | RP2040 UART1 polling adapter with explicit claim/release |
| `stm3_client.h/.c` | Portable blocking COBS/CRC request/replay client |

The resident STM32 runtime owns the keyboard, PMU, USART3 and its DMA channels.
Native modules execute from SRAM and receive bounded job input/output plus a
microsecond clock callback. Modules are trusted cooperative code: slice overrun
is checked after returning; native memory isolation and forced preemption are
not supplied by this ABI. The resident build and deployment notes remain in
`research/picocalc-stm32-runtime-20261107`; they are not build dependencies of
this SDK or of production audio code.

## Module contract

Target `0x70301` means Cortex-M3/Thumb-2, soft ABI. The package starts with the
64-byte little-endian S3M1 header defined in `stm3_module.h`, followed by the flat
image and sorted ABS32 relocation offsets. Code+BSS are limited to6144 bytes;
input and output are512 bytes each. A native call declares a maximum slice of
at most2000µs. `INIT` may complete the job immediately or request subsequent
`STEP` calls; the host regains control between calls.

Link the module with `module.ld`, normally using GCC `-mword-relocations` and
`--emit-relocs`. Load-address-dependent ABS32 words must refer within the flat
image+BSS; branch/relative relocations remain relative. `elf32.py` exposes
sections, symbols and relocations for a packager to validate. It is a build tool
for compiler-produced files, not an untrusted ELF validation boundary.

## Wire contract

Frames are COBS-encoded and zero-terminated; a leading zero is accepted for
resynchronization. The decoded header is8 bytes:
`version:u8=1, command:u8, sequence:u16, payload_bytes:u16, flags:u16=0`.
It is followed by up to256 payload bytes and a reflected CRC32 over header and
payload (polynomial0xEDB88320, initial/final XOR0xFFFFFFFF). Responses use
`command|0x80`; the first payload word is a status code. READ therefore returns
at most252 useful bytes per frame. The encoded-frame buffer limit is272 bytes.

Commands are HELLO1, LOAD_BEGIN2, LOAD_CHUNK3, LOAD_COMMIT4, WRITE5, START6,
STATUS7, READ8, CANCEL9, UNLOAD10 and optional START_RESULT11. READ accepts finished jobs. There is one
module and one job at a time. Identical sequence/command/CRC replay resends the
cached reply without repeating START. The STM32 does not send unsolicited data.

The transport is stop-and-wait: the runtime's cached reply stays pinned through
TX DMA, and it does not process the next request while DMA still owns that
reply. A new sequence is for a new operation; retries reuse the original frame.
An asynchronous backend must preserve these lifetimes and framing constraints.

START_RESULT requires bit2 (`4`) in HELLO's transport flags. Its four input
words are `module_id, input_bytes, deadline_ms, result_bytes`; the input buffer
is filled with WRITE as before. The module starts once. On completion the
STM32 sends the single pending response: status, job ID, maximum slice time
in microseconds and the requested prefix of output (at most244 bytes).
There is no initial acknowledgement and no STATUS/READ readiness polling.
INIT/STEP/deadline failures return their original status instead of samples.
The native2ms slice limit and keyboard processing between module calls remain.

Only one request may be outstanding. An identical pending replay waits for
the same job; a completed replay resends the exact cached bytes. A different
request while completion is pending is ignored and counted as a sequence
conflict. The requested job deadline bounds this interval. Clients must not
issue CANCEL/HELLO with a new sequence before the pending reply/deadline;
transport retries reuse the original frame. Long outputs can be read in
further ordinary READ chunks after the completion response has arrived.
Legacy commands retain their meanings; clients must mask known HELLO bits
rather than requiring the complete flags word to equal3.

The completion extension has passed host sanitizer and relocated Thumb-2
tests. It has not yet been verified on physical hardware. Original physical
evidence below describes the earlier resident, without this extension.

## RP2040 ownership

`stm3_pico_uart1_begin` requires a zero-initialized adapter, PERI48MHz,
nominal2250000baud, an inactive UART1 and GPIO8/9 in the unclaimed NULL function.
It uses GP8 TX / GP9 RX, connected to STM32 USART3 PC11 RX / PC10 TX on PicoCalc.
It refuses another owner's mux/UART configuration. The actual Pico divisor is
IBRD1/FBRD21, approximately2258823baud; STM32 uses2250000baud.

`stm3_pico_uart1_end` restores the pin mux, pads, UART configuration and previous
UART reset state. The adapter does not claim DMA or alter UART0, I²C, CPU clocks
or the rest of the reset register. Its timeout clock must advance independently
of any service callback; the tested APP uses the RP2040 hardware timer.

The provided client is blocking and suits diagnostics or small transactions.
The production Spectrum audio backend uses its own asynchronous/DMA adapter;
only one adapter may own UART1/GP8/GP9 at a time. Its scheduling and DMA resource
allocation belong to that backend. These files do not install firmware or
automatically claim hardware when linked.

## Existing evidence

The physical Pico-to-STM32 test loaded, ran, replayed and unloaded the module,
checking64 int64-reference dot-product rows with zero UART errors. Separate
tests exercised READ sizes0..252, COBS framing, CRC rejection, timeouts,
ownership refusal and register restoration. A DWT test measured the M3 kernels;
a512-byte block diagnostic transferred32768 verified bytes at86.4KB/s useful
payload with the blocking client. That is a diagnostic result, not an audio
renderer or asynchronous-throughput guarantee. The detailed original receipts
are referenced by `PROVENANCE.json`.
