# Pinned native STM32F401/F411 header SDK

This header-only snapshot makes native firmware builds independent of an
installed STM32duino package. It contains the transitive headers used by the
qualified F401/F411 C, C++ and assembler sources, plus the F401xE device header.
No vendor implementation, startup, HAL driver, Arduino Core or DSP library
is compiled.

The snapshot preserves the previously qualified header bytes: CMSIS Core
6.2.0 and the ST device/HAL/USB headers distributed with STM32duino 2.12.0.
The six USB interface headers preserve existing declaration/layout contracts;
all runtime implementations are the project's owned STM32 USB code.
STM32duino is recorded as provenance only and is not needed at build time.

Component upstream locations, revisions and SHA256 for every shipped header
and license are in `manifest.json`. Original notices and licenses are retained
under each component. CMake and native dependency preflight verify all hashes.
Update the snapshot deliberately together with build/ARM and image-equivalence
tests; do not regenerate it from whatever SDK happens to be installed locally.

Default native builds use this directory. `--sdk`, `-SdkPath` or
`MK61_GCC_SDK` may select another copy with a valid pinned manifest. GNU Arm GCC
is selected independently using its explicit path, `MK61_GCC_TOOLCHAIN`,
the project's `.build/toolchains` cache or PATH.

The repository marks this snapshot as non-normalized Git text so Windows
core.autocrlf cannot change the bytes covered by the manifest. The SDK self-test
performs a fresh Git checkout with core.autocrlf=true and revalidates every hash.
