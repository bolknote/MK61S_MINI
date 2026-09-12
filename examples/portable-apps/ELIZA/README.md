# ELIZA.APP

Compact standalone ELIZA/DOCTOR for the MK61S portable APP ABI.  The built-in
fixed script preserves the characteristic mechanisms of the 1966 DOCTOR
script: ranked keywords, captured phrase tails, rotating replies, pronoun
reflection, a small memory and repeated-input detection.  It is not a MAD-SLIP
interpreter and does not include the original script editor.

The response tables are based on the DOCTOR transcription published by the
Critical Code Studies Lab:
<https://github.com/critical-code-studies/ELIZA/blob/main/sources/DOCTOR.txt>.

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

python3 tools/build_portable_app.py --name ELIZA \
  --source examples/portable-apps/ELIZA/main.c \
  --source examples/portable-apps/ELIZA/eliza_engine.c \
  --output-dir .build/portable-apps/eliza

cp .build/portable-apps/eliza/ELIZA.APP programs/app/ELIZA.APP
```

The ready-to-copy result is `programs/app/ELIZA.APP`.  On the repository's
sample C5 layout it is installed as `/app/ELIZA.APP`.
