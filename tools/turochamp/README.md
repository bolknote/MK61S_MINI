# Turochamp for TinyBASIC

This directory assembles the BASIC game in `programs/games/Turochamp`.
The templates in `basic/` contain the chess implementation. Python only
resolves array names, labels and the M61 call/return protocol; the device
executes every rule, evaluation and search operation in its built-in BASIC.
Leaf services marked `LOCAL` become BASIC GOSUBs, avoiding an M61 reload.
Their bodies have no M61 calls and are expanded from one shared template.
The BASIC uses ON GOTO/GOSUB for return phases, glyphs and menu dispatch.
DATA/READ initializes the back rank and move offsets; ELSE selects the
board orientation heading. These require the extended TinyBASIC syntax.

Reference: Martin C. Doege's public-domain `PyTuroChamp/pyturochamp.py`,
which also underlies the supplied nimTUROCHAMP application. The historical
seven positional criteria are included. Search defaults to two full plies
and eight total plies, matching the reference application's configuration.
The move generator enforces legal chess, including all four promotions,
castling and en passant. The two search depths are algorithm parameters.

This is a reconstruction, not recovered original code. Like PyTuroChamp,
material is compared by difference rather than the historically described
ratio. Positional mobility is pseudo-mobility, captures count twice and
each square root is rounded to a tenth. Pawn credit, non-pawn defenders,
rook/bishop/knight safety, king mobility and the hypothetical queen on the
king's square implement the published criteria. A mating threat is one
boolean bonus, tested on the scoring side's hypothetical next legal turn.
Immediate castling is also tested for that side; these avoid the Python
reference's use of the opponent's turn after the candidate move. The
retained-rights castling bonus follows the reference, including pawn moves.

The search extends check evasions and tactical positions following a
defended capture or a check. Selective moves include captures and all
promotions; a quiet selective position allows stopping at its material
value. Captures precede quiet moves, with alpha-beta pruning. The root adds
the candidate's positional change and castling bonuses to material times
1000; equal scores are resolved by file/rank coordinates. Two full plies
and eight total plies are the shipping configuration.

The mailbox board has 120 cells. A reversible move is stored losslessly as
12 bits, four moves per double, so the 150-ply repetition history uses just
38 array elements. No probabilistic hashes are used for adjudication.
An irreversible pawn move, capture or change of castling rights resets the
repetition segment. Castling-right changes do not reset the 50-move clock.
The search restores board, clocks, castling rights, EP and history. Claims
can be made in the current position or by announcing an intended legal
move. Threefold/50-move claims are optional; fivefold/75-move draws are
automatic and mate has priority. Proven dead-material classes include
bare kings, one minor and only bishops on the same square colour. KNN-K
is not automatically declared drawn. The menu also offers agreement and
resignation, and can restart a game.

The 7x7 local font contains both piece colours on both square colours,
and selected-cell variants. The complete board and coordinates occupy
63x63 pixels of a UC1609, with status text to the right.
Arrow keys move horizontally, step keys vertically, and OK selects a piece
and its destination. Promotion choices include queen, rook, bishop and knight.

Assembly:

```
python3 tools/turochamp/assemble.py
python3 tools/turochamp/assemble.py --check
python3 tools/turochamp/font.py
python3 tools/turochamp/font.py --check
```

Each part retains room for `@(0)..@(351)`, fits in 192 lines and in one
3584-byte C6 BASIC file. Array storage remains shared between M61 parts.
There is no native chess engine, website access or opening-book dependency
at game runtime.

Verification:

```
python3 -m venv /private/tmp/turochamp-test-env
/private/tmp/turochamp-test-env/bin/pip install -r tests/turochamp-requirements.txt
TUROCHAMP_PYTHON=/private/tmp/turochamp-test-env/bin/python bash tests/run_turochamp_tests.sh
```

`--selfplay` adds a complete computer-versus-computer game with the shipping
2/8-ply search. The harness compiles the actual device BASIC, transports
FEN and key events, and runs both the interpreter and bytecode VM. Python
chess supplies independent legal move sets, standard perft positions,
seeded games, state restoration and adjudication checks. A separate
bitboard evaluator checks every positional criterion; an exhaustive
reference search checks material/positional scores. Keyboard tests execute
side selection, moves, castling, EP, promotion, claims, resignation,
agreement, help, restart and pixel-cell layout. No host chess code makes
decisions for the BASIC engine.

The package check needs only standard Python:
`python3 tests/turochamp_package_self_test.py`. It checks generated files,
M8/UTF-8/CRLF quotas, dispatcher coverage, call depth, font CRC and all
normal/selected cell rasters. Device timing needs a live UC1609 calculator;
host timings do not include flash reads or APP handoffs.
