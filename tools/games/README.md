# MK61S Game Library

`games.cmd` is a cross-platform checklist for fetching third-party game data
and building game-related PicoCalc APPs. Downloaded binaries and build outputs
stay under `.build/game-library` or an existing ignored third-party cache; they
do not belong in Git.

```sh
./tools/games.cmd
./tools/games.cmd list
./tools/games.cmd run --select another-world-en --dry-run
./tools/games.cmd run --select spectrum-ianna --select build-spectrum-app
```

The interactive menu uses Up/Down, Space, Enter and Esc/Q. On Unix it needs
Bash and Python 3.10+. On Windows the launcher uses a native PowerShell 5.1+
implementation for catalog parsing, HTTP, SHA-256 and ZIP extraction; Python
is not required.

The ready-to-copy tree is `.build/game-library/sd`. Copy its folders to the
microSD root. Launch a title from **Explorer → Games** with Enter. Cached downloads and
source manifests are kept next to it. `catalog.json` pins source URLs, archive
hashes and, where applicable, every extracted member. Add a catalog entry only
after checking its redistribution or user-download terms; a download source is
not automatically a licence.

For Another World select both the DOS data and `Build ANOTHER.APP`. Both go to
`Games/Another World`. The catalog
extracts only `MEMLIST.BIN` and `BANK01` through `BANK0D`. The source site's
"abandonware" label is not treated as permission to redistribute those files.
It also builds `AWCACHE.BIN` locally from the sound resources on both Unix
and Windows. Keep it beside the original files when copying the folder to the
card. It is optional: the APP checks the cache against the original resources
and falls back to them when the cache is absent or does not match. To rebuild
it for an existing local copy on either platform, run
`tools/games.cmd prepare-another path/to/ANOTHER`.
The APP has been tested on PicoCalc. It currently mixes mono audio on the Pico;
the experimental M3 audio backend is not connected to the APP.

The current `ANOTHER.APP`, `SPECTRUM.APP` and PicoCalc `URQ.APP` orchestration uses their
existing Python builders, so those build checkboxes are shown on
macOS/Linux only. Windows still downloads and verifies the selected game
sources natively.

The Spectrum entries delegate to the established pinned downloader. When all
three Spectrum packages and `Build SPECTRUM.APP` are selected together, look for
**Spectrum Collection** in Games. Inside the mounted image, select games using
the esxDOS browser. The emulator and its ROMs go in `Programs/Spectrum`.
Selecting fewer games only warms the verified local package cache.
