# Stock Explorer icons

Original monochrome artwork, under the repository's license. Each icon is a
32×32 WBMP Type 0 file: four header bytes and 128 pixel bytes, 132 bytes total.
There is no antialiasing, font dependency or runtime scaling. Explorer renders
the black source pixels as foreground ink, so the same asset serves PicoCalc
320×320 and Classic 192×64.

The 27 drawings cover all 23 directories shipped from `programs/`, plus the
generated `apps`/`Apps`, `System`, `System/VMCache`, `licenses` and
`licenses/ui-fonts` directories. The applications icon is shared by `app`,
`apps` and `Apps`. Every game has its own drawing. The previously reviewed
Turochamp, High Noon and Runner bitmaps remain byte-for-byte unchanged.

`dev/tools/explorer_icons.py` contains the integer-pixel drawing recipes and the
explicit directory-to-icon map. To regenerate or check the committed assets:

```sh
python3 dev/tools/explorer_icons.py --generate
python3 dev/tools/explorer_icons.py --check
python3 tests/explorer_icons_self_test.py
```

`--preview <image.png>` produces a labelled review sheet with Pillow; its
nearest-neighbour enlargement is for review only. Generation and packaging use
only the Python standard library.

Every source directory contains its own `autoexec.wbmp`. Pico and STM32 bundle
builders copy the appropriate artwork into generated directories too. System
installers transfer these optional binary resources and verify their readback;
an older package without icons does not delete existing device icons. Folder
icons do not contain executable code or alter autoexec selection.

CI checks the mapping against every `programs/` directory, verifies the exact
assets, and exercises the stock bitmaps through the real WBMP decoder and both
native screen layouts. A new shipped directory needs an explicit icon mapping.
