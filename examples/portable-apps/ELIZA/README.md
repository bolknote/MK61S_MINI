# ELIZA.APP

Exact fixed-script port of the 1966 ELIZA/DOCTOR conversation engine for the
MK61S portable APP ABI. It implements the original keyword stack and ranks,
word substitution, decomposition/reassembly matching, rotating replies,
`=KEY`, `NEWKEY`, `PRE`, `DLIST`, the four-state `LIMIT` counter and the
recovered IBM 7094 Hollerith memory hash.

The original DOCTOR S-expression is checked in as `doctor-1966.txt`. The
offline generator compiles it to bytecode so the device does not spend APP
space on a general MAD-SLIP list processor or script editor; this changes the
representation, not the DOCTOR rules or their runtime behavior. Within the
device bounds of 95 input bytes, 191 reply bytes and sixteen pending memories,
responses follow the reference implementation exactly.

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
configuration with loadable BASIC or FOCAL).

On the 192x64 display, the two opening help cards use the resident compact
Pixel font and clearly boxed key labels.  Older or character-only firmware
automatically receives the fixed-grid text version instead.

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

The ready-to-copy result is `programs/app/ELIZA.APP`.  On the repository's
sample C5 layout it is installed as `/app/ELIZA.APP`.

The host test contains the complete conversation printed in the January 1966
CACM paper plus the reference implementation's comprehensive DOCTOR coverage
transcript. Development was also checked differentially against that reference
on deterministic mixed-keyword conversations.
