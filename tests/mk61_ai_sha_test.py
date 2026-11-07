#!/usr/bin/env python3
"""Independent hashlib oracle for the read-only on-device model SHA probe."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import random
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().with_name("mk61_ai_file_hash_probe.c")
    with tempfile.TemporaryDirectory(prefix="mk61ai-sha-test-") as directory:
        library = Path(directory) / "probe.so"
        subprocess.run(["clang", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-DMK61_AI_SHA_HOST_ONLY", "-shared", "-fPIC", str(source), "-o", str(library)], check=True)
        function = C.CDLL(str(library)).mk61_ai_sha256
        function.argtypes = [C.c_void_p, C.c_uint, C.c_uint, C.c_void_p]
        rng = random.Random(61)
        samples = [b"", b"abc", b"a" * 1000000,
                   *(rng.randbytes(n) for n in [1, 55, 56, 63, 64, 65, 127, 128, 512, 4096, 4097]),
                   args.package.read_bytes()]
        count = 0
        for data in samples:
            for chunk in [1, 17, 64, 4096]:
                memory, digest = C.create_string_buffer(data), C.create_string_buffer(32)
                function(memory, len(data), chunk, digest)
                assert digest.raw == hashlib.sha256(data).digest(), (len(data), chunk)
                count += 1
    print(json.dumps({"cases": count, "passed": True, "package_sha256": hashlib.sha256(samples[-1]).hexdigest()}))


if __name__ == "__main__":
    main()
