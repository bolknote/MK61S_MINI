#!/usr/bin/env python3
"""Compare the dependency-free Windows packer with the native ZX0 reference."""
from itertools import product
from pathlib import Path
import os
import random
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

if not shutil.which("pwsh"):
    print("pwsh unavailable; .NET optimal packer check skipped")
else:
    with tempfile.TemporaryDirectory(prefix="mk61-optimal-dotnet-") as tmp:
        work = Path(tmp)
        reference = work / "packer"
        env = dict(os.environ, MK61_MODULE_PACK_BIN=str(reference))
        subprocess.run(["bash", str(ROOT / "tools/build_mk61_module_pack.sh"),
                        "--help"], env=env, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        fixtures = [bytes(bits) for length in range(1, 7)
                    for bits in product((0, 1), repeat=length)]
        rng = random.Random(6132)
        fixtures += [rng.randbytes(size) for size in (7, 31, 128, 257, 4096)]
        fixtures += [(bytes(range(period)) * ((size + period - 1) // period))[:size]
                     for period in (1, 2, 7, 31) for size in (257, 1024, 20480)]
        # Interleaved literal runs, branches and competing match offsets.
        fixtures += [(b"\x00\xf0\x04\xf8" + bytes(range(32)) + b"abcabcxabcabc") * 80]
        for index, payload in enumerate(fixtures):
            (work / f"{index:03}.bin").write_bytes(payload)
        (work / "empty.rel").write_bytes(b"")
        script = work / "pack.ps1"
        script.write_text('''param([string]$Source, [string]$Fixtures)
$ErrorActionPreference = 'Stop'
Add-Type -Path $Source
foreach ($image in Get-ChildItem -LiteralPath $Fixtures -Filter '*.bin') {
    $result = [Mk61.Build.AppPacker]::PackFile('app', $image.FullName,
        (Join-Path $Fixtures 'empty.rel'), [int]$image.Length, 0,
        0x20000000, $null, ($image.FullName + '.dotnet.APP'))
}
''')
        subprocess.run(["pwsh", "-NoLogo", "-NoProfile", "-File", str(script),
                        str(ROOT / "tools/.mk61-app/Mk61AppPacker.cs"), str(work)],
                       check=True)
        for index, payload in enumerate(fixtures):
            image = work / f"{index:03}.bin"
            app = work / "reference.APP"
            subprocess.run([str(reference), "--kind", "app", "--image", str(image),
                            "--relocations", str(work / "empty.rel"),
                            "--memory-size", str(len(payload)), "--entry-offset", "0",
                            "--output", str(app)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            assert app.read_bytes() == Path(str(image) + ".dotnet.APP").read_bytes(), index
        print(f".NET optimal ZX0: {len(fixtures)} complete APPs match native reference PASS")
