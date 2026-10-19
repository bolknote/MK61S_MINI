# ELIZA.APP

Exact fixed-script port of the 1966 ELIZA/DOCTOR conversation engine for the
MK61S portable APP ABI. It implements the original keyword stack and ranks,
word substitution, decomposition/reassembly matching, rotating replies,
`=KEY`, `NEWKEY`, `PRE`, `DLIST`, the four-state `LIMIT` counter and the
recovered IBM 7094 Hollerith memory hash.

The original DOCTOR S-expression is checked in as `doctor-1966.txt`. The
offline generator compiles it to bytecode so the device does not spend APP
space on a general MAD-SLIP list processor or script editor; this changes the
representation, not the DOCTOR rules or their runtime behavior.

Memories are kept as variable-length FIFO records in the resident 8192-byte
WORKSPACE arena, mirroring the original dynamically sized SLIP `MYLIST`.
There is no separate record-count limit: only the total encoded byte size
matters (the stress test retains and recalls 256 ordinary memories in order).
The calculator editor accepts 511 input bytes. The 1151-byte reply buffer is
sized above the worst word-substitution expansion plus the longest fixed
DOCTOR reassembly for an accepted input, so replies are not truncated. These
byte ceilings come from the MK61S memory and stack budgets, not from
Weizenbaum's source.

The script and expected transcripts come from Anthony Hay's CC0 ELIZA
recreation, revision `0d34ebc234090a417755afe8fe4a31f75e2e55bf`:
<https://github.com/anthay/ELIZA>.

## Controls

Text uses direct multi-tap SMS entry:

- `1` PQRS, `2` TUV, `3` WXYZ
- `4` GHI, `5` JKL, `6` MNO
- `7` space, `8` ABC, `9` DEF
- `0` commits the current letter
- `Cx` erases, arrows move the cursor, `OK` sends, `ESC` exits

The APP deliberately calls the resident editor so its cursor, timing and
LCD1602 horizontal viewport are identical to BASIC and FOCAL.  Consequently it
needs a firmware/System APP set exposing `MK61_SERVICE_CAP_EDITOR` (the normal
configuration with loadable BASIC or FOCAL). It also leases the standard
`MK61_SERVICE_CAP_MEMORY` WORKSPACE arena for the duration of the conversation.

On the 192x64 display, the two opening help cards use the resident compact
Pixel font and clearly boxed key labels.  Older or character-only firmware
automatically receives the fixed-grid text version instead.

The native PicoCalc build uses the resident Ark Pixel 16px strike for help,
input and replies. It draws at 1:1 pixels into the host's borrowed 320x320
bitmap. Replies wrap at actual glyph advances in a 304px text area; long words
and responses continue over as many pages as necessary. The input viewport
follows the cursor through all 511 accepted bytes, including wide letters.
Editing, SMS timing and DOCTOR rules still use the shared editor and engine.
Enter sends input or advances a page; Escape exits. The APP's font choice
does not change the calculator's saved font settings. The STM32 presentation
keeps its existing text and graphical layouts.

## Build and test

```sh
bash tests/run_eliza_app_tests.sh

python3 tools/generate_eliza_doctor.py --check

python3 tools/build_portable_app.py --name ELIZA \
  --source examples/portable-apps/ELIZA/main.c \
  --source examples/portable-apps/ELIZA/eliza_engine.c \
  --output-dir .build/portable-apps/eliza

cp .build/portable-apps/eliza/ELIZA.APP programs/app/ELIZA.APP
```

The ready-to-copy result is `programs/app/ELIZA.APP`. On C6 it is installed as
`/app/ELIZA.APP`.

The host test contains the complete conversation printed in the January 1966
CACM paper plus the reference implementation's comprehensive DOCTOR coverage
transcript. Development was also checked differentially against that reference
on deterministic mixed-keyword conversations, a 510-character input and a
256-memory FIFO stress session.
