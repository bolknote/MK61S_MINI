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

The ready-to-copy tree is `.build/game-library/sd`. Cached downloads and
source manifests are kept next to it. `catalog.json` pins source URLs, archive
hashes and, where applicable, every extracted member. Add a catalog entry only
after checking its redistribution or user-download terms; a download source is
not automatically a licence.

Another World is intentionally data-only until the native APP exists. The
catalog extracts only `MEMLIST.BIN` and `BANK01` through `BANK0D`, which are the
resource files needed by the known engine reimplementations. The source site's
"abandonware" label is not treated as permission to redistribute those files.

The current `SPECTRUM.APP` and PicoCalc `URQ.APP` orchestration uses their
existing Python builders, so those two build checkboxes are shown on
macOS/Linux only. Windows still downloads and verifies the selected game
sources natively.

The Spectrum entries delegate to the established pinned downloader. When all
three Spectrum packages and `Build SPECTRUM.APP` are selected together, the
resulting APP folder also receives the built `GAMES.img`; selecting fewer games
only warms the verified local package cache.
