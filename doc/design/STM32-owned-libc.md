# Native strings and retained storage

The native resident links with `-nostdlib` and no C/C++/math/compiler runtime
archive members. This phase replaces the remaining newlib strings and the
single lifetime-allocation use of nano malloc. Existing word memcpy, memmove,
memset and memcmp are unchanged. CMSIS definitions and the five USB/LL source
files remain until the USB phase.

| Board | Flash before | Flash after | Static RAM before | Static RAM after | CRC |
|---|---:|---:|---:|---:|---|
| Classic V3 UC1609 | 361336 | 360920 | 28560 | 28464 | BDB8BB8C |
| mini V3 LCD1602 A00 | 333824 | 333408 | 27224 | 27128 | 8C1AA83C |

Both boards save **416 Flash bytes and 96 static RAM bytes**. These numbers
exclude separately allocated retained buffers. Their sizes and cache capacities
are unchanged; removing allocation headers also releases a small amount of
heap space. ELF qualification now reserves their exact rounded native sizes,
without the previous conservative 32-byte malloc allowance per buffer.

`system_strings.c` implements strlen, strnlen, strchr, strcmp, strncmp, strcpy,
strncpy, strncat and memchr. Unsigned-byte comparison, terminators, padding,
return pointers and bounds follow their C contracts. Byte access avoids reading
past a string's allocation or guard page. The source is built without LTO or
builtin-loop substitution, preventing accidental recursive libc calls.

`allocate_retained_buffer` allocates through the existing shared-memory heap
boundary, with eight-byte alignment, zeroing and at most one reclaim of an
idle OVERLAY cache. Failure does not advance the heap. Active APP memory, pinned
staging, interrupt context and eviction callbacks retain their protections.
These buffers are allocated once and never freed; a general malloc/free heap
and its metadata are unnecessary. Legacy Arduino builds keep their old path.

The linker script also stops naming standard archives in `/DISCARD/`: GNU ld
could extract a dead memchr object even under `-nostdlib` when it encountered
those filenames. Actual per-image archive gates now reject every standard
runtime object in all 27 checked ELFs, including the variant without LTO.
Explicit GNU-libm control builds remain available and pass the math oracle.

## Qualification

- Host ASan/UBSan: nine string operations against the host library, byte values,
  alignment, short/long bounds and exact protected-page tails; retained allocator
  alignment/zeroing/padding, exhaustion, APP/cache pinning and callback isolation.
- The entire previous memory-buffer, dynamic APP, overlay and qualified-budget
  suite passes with sanitizers.
- Actual ARM strings: Classic 12000 calls, mini 10500, no-LTO variant 10500;
  a standalone image retaining all nine functions passes 13500. Read and write
  hooks enforce valid input/destination/stack ranges; independent byte oracles
  check contents, terminators and unsigned order, plus callee-saved GPRs and SP.
  Unused, unexported functions are allowed to disappear from production images.
- Both production ELFs pass 1897 high-precision math vectors and 54 IEEE cases;
  three service APPs run at three load addresses with register/bounds checks.
  No mathematical kernels or caches were changed in this phase.
- All 16 F411 and 9 F401 configurations build; no libgcc, libm, libstdc++,
  libc_nano, libc or libnosys object is included in any native target.
- Both physical devices pass 4-KiB MSC import/export with Unicode names,
  two CDC/MSC switches, reset and cleanup; minimum observed remaining stack is
  12628 bytes Classic and 12544 mini (required 12288).
- Both physical displays/USB screen pass 100 complete independently generated
  frames. The pre-existing USB-screen cleanup issue still uses the explicitly
  recorded zero-state reset workaround, pending the USB phase.
- Twelve ADC probes, five restored emulator batches and 100 NOR reads per board
  pass without SPI/DMA errors. 60-sample 64-KiB read medians are 24988.5 us and
  24767 us. Emulator medians are 1712125 and 1711105 cycles per step, within
  0.2% of the prior phase's measurement; its source and caches are unchanged.
- Full original file fingerprints, active program, registers, stack and working
  directory are checked against the fresh snapshots from this task.

```sh
tests/run_native_libc_tests.sh
MK61_TEST_SANITIZERS=1 tests/run_memory_buffer_tests.sh
python3 tests/native_strings_arm_self_test.py --elf BUILD/resident.elf
python3 tests/check_native_runtime_libraries.py BUILD/resident.map --without-libc
```

`MK61_USE_NATIVE_LIBC=0` provides a control with the previous allocator and
newlib strings. The native build normally uses all three owned options for
libm, EABI and libc; turning off compact libm deliberately retains GNU libraries
for numerical comparisons. Zero archive members is a link result, not a claim
that all underlying algorithms were invented here: the EABI fast assembly's
GCC attribution remains explicit.

Real RTC/keyboard STOP against host suspend is deferred until the final USB
qualification, as agreed. USB specialization and that manual scenario remain.
