"""Check all calculator launchers, storage limits and unchanged game code."""
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "programs/games"
# Startup/game lines before the OK-help change, excluding viewer setup and ret.
STARTUP = {
    'Bumblebee': '301914d37f3973906446e92922cefc2d894dfaca237bab301a9c6486699ae27b',
    'Bumblebee Fly': 'a5a66eb3e162e4009348d1b67ed241e7bdb68159986cbf5d2642c6837fc43f89',
    'Chase HQ': 'd2fe8985987e92a8836d55cc2a46e10e56f3ca68793f3f386736bd6cf613d112',
    'ELITE': '17b90407df36c0053989f3f764922e4962e970ad2de70057784920c3089eb08f',
    'Fox Hunting': '4b6e9882b1eb03a1701f29686013f4dd0ca48c34c62d172b421d2f31d981bf4d',
    'Infinity Story': '1d5649f8371f4062021dbe9a65fba4981240d713390b350e18369d52ab30a41d',
    'Lunolet 1': '88bb1d43c4c997712222ee19eee4a423bd3a339c81df843ca66a61fbd0a7fd97',
    'Mult Lunolet': 'd2fb2544b5ede0d45710fd25dddc8c82845559dcc8095972a7a73749bc482c23',
    'Naval Battle': '09f146128f4108e9beb35c74fa6d2ea3b6c82ee769d24243fd1d68ccf64e17f5',
    'Pogonya': '8627675a2df2114f55b48c809aa0d06c7cbc83bcba619c1c2fd960925c20d5aa',
    'Samurai': '290a90a233ff3538b9916b3dd7f3c5a67d15bd226b306579bff1a29e45b72a4a',
    'Wumpus': '60199a657c933147406227d8fc3276d4557454f79405fa35379397be74bb3a08',
}

for name, expected in STARTUP.items():
    game = ROOT / name
    raw = (game / "autoexec.m61").read_bytes()
    assert len(raw) <= 1536, (name, "M61 storage limit", len(raw))
    source = raw.decode("ascii")
    main, helper = source.split("\n:help\n")
    lines = main.splitlines()
    assert lines[0] == "open? manual.md", name
    assert lines.count("bind OK run :help") == 1, name
    assert lines[-1] == "ret" or lines[-2:] == ["ret", ""], name
    if "reinit" in lines:
        assert lines.index("reinit") < lines.index("bind OK run :help"), name
    expected_helper = ["open? manual.md", "ret"]
    if name == "Bumblebee":
        expected_helper.insert(1, "print off")
    assert helper.splitlines() == expected_helper, name
    assert (game / "manual.md").is_file(), name
    startup = "\n".join(line for line in lines
                        if line and not line.startswith(("open", "bind OK"))
                        and line != "ret")
    assert sha256(startup.encode()).hexdigest() == expected, (name, "game changed")

assert "bind OK" not in (ROOT / "High Noon/autoexec.m61").read_text()
print("game manuals: 12 OK bindings, unchanged startup/code, storage limits: ok")
