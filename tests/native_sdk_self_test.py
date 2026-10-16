#!/usr/bin/env python3
"""SDK corruption, path isolation, tool lookup and offline installer regressions."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native_sdk", ROOT / "tools/.mk61-gcc/native_sdk.py")
sdk = importlib.util.module_from_spec(spec); spec.loader.exec_module(sdk)
gate_spec = importlib.util.spec_from_file_location("sdk_gate", ROOT / "tests/check_standalone_sdk_build.py")
gate = importlib.util.module_from_spec(gate_spec); gate_spec.loader.exec_module(gate)
original = ROOT / "third_party/stm32f4"
assert sdk.validate_sdk(original) == original.resolve()
manifest = json.loads((original / "manifest.json").read_text())
assert set(manifest["files"]) == {p.relative_to(original).as_posix() for p in original.rglob("*") if p.is_file() and p.name not in ("manifest.json", "README.md")}
assert all(not name.endswith((".c", ".cpp", ".S")) for name in manifest["files"])
lock = json.loads((ROOT / "tools/.mk61-gcc/toolchain-lock.json").read_text())
contract = json.loads((ROOT / "tools/release-contract.json").read_text())
assert lock["version"] == contract["toolchain"]["gnu_arm"]
assert set(lock["assets"]) == {"darwin-arm64", "darwin-x64", "linux-arm", "linux-arm64", "linux-x64", "win32-x64"}
for asset in lock["assets"].values():
    assert len(asset["sha256"]) == 64 and int(asset["sha256"], 16)
    assert asset["url"] == "https://github.com/xpack-dev-tools/arm-none-eabi-gcc-xpack/releases/download/v" + lock["version"] + "/" + asset["archive"]

# Native cases are explicit; a legacy Arduino case must fail before tool lookup.
legacy = next(case["id"] for case in contract["cases"] if case["builder"] == "arduino")
result = subprocess.run([sys.executable, str(ROOT / "tools/.mk61-gcc/build-standalone.py"),
                         "--release-case", legacy, "--build-path", "/unused", "--check"],
                        capture_output=True, text=True)
assert result.returncode != 0 and "requires a native GCC case" in result.stderr

def failed(call, expected):
    try:
        call()
    except (ValueError, OSError) as error:
        assert expected in str(error), str(error)
    else:
        raise AssertionError("invalid dependency was accepted: " + expected)

with tempfile.TemporaryDirectory(prefix="mk61 native SDK Юникод ") as temporary:
    work = Path(temporary)
    # Real Git checkout with Windows autocrlf must preserve pinned SDK bytes.
    fixture = work / "git fixture"
    shutil.copytree(original, fixture / "third_party/stm32f4")
    shutil.copy2(ROOT / ".gitattributes", fixture / ".gitattributes")
    subprocess.run(["git", "init", "--quiet", str(fixture)], check=True, capture_output=True)
    git = ["git", "-c", "core.autocrlf=true", "-C", str(fixture)]
    subprocess.run([*git, "add", "--force", ".gitattributes", "third_party/stm32f4"], check=True, capture_output=True)
    checkout = work / "fresh checkout"
    subprocess.run([*git, "checkout-index", "--all", "--prefix=" + checkout.as_posix() + "/"], check=True, capture_output=True)
    sdk.validate_sdk(checkout / "third_party/stm32f4")

    copy = work / "SDK with spaces"
    shutil.copytree(original, copy)
    def cmake(ok, message=""):
        result = subprocess.run(["cmake", "-DMK61_PROJECT_ROOT=" + str(ROOT), "-DMK61_SDK_ROOT=" + str(copy), "-P", str(ROOT / "tools/.mk61-gcc/native-sdk.cmake")], capture_output=True, text=True)
        assert (result.returncode == 0) == ok, result.stdout + result.stderr
        if message:
            assert message in result.stdout + result.stderr, result.stdout + result.stderr
    cmake(True)
    header = copy / "device/include/stm32f411xe.h"
    raw = header.read_bytes()
    header.write_bytes(raw + b"\n")
    failed(lambda: sdk.validate_sdk(copy), "checksum mismatch")
    cmake(False, "checksum mismatch")
    header.write_bytes(raw)
    header.rename(header.with_suffix(".missing"))
    failed(lambda: sdk.validate_sdk(copy), "file is missing")
    cmake(False, "file is missing")
    header.with_suffix(".missing").rename(header)
    invalid = json.loads((copy / "manifest.json").read_text())
    invalid["files"]["../escape.h"] = "0" * 64
    (copy / "manifest.json").write_text(json.dumps(invalid))
    failed(lambda: sdk.validate_sdk(copy), "Invalid native SDK file path")
    cmake(False, "Invalid native SDK file path")
    (copy / "manifest.json").write_bytes((original / "manifest.json").read_bytes())

    tool_root = work / "GNU Arm"
    tool_bin = tool_root / "bin"; tool_bin.mkdir(parents=True)
    suffix = ".exe" if os.name == "nt" else ""
    for name in ("gcc", "g++", "ar", "ranlib", "objcopy", "size", "nm", "objdump", "c++filt"):
        (tool_bin / ("arm-none-eabi-" + name + suffix)).write_bytes(b"fixture")
    with mock.patch.dict(os.environ, {"MK61_GCC_CORE": "/poisoned/package", "MK61_GCC_TOOLCHAIN": str(tool_root)}):
        with mock.patch.object(Path, "home", side_effect=AssertionError("must not inspect a user Arduino installation")):
            assert sdk.find_toolchain(work, lock["version"]) == tool_bin.resolve()
            explicit = work / "Explicit GNU Arm"
            shutil.copytree(tool_root, explicit)
            assert sdk.find_toolchain(work, lock["version"], explicit) == (explicit / "bin").resolve()
    with mock.patch.dict(os.environ, {"MK61_GCC_TOOLCHAIN": ""}), mock.patch.object(sdk.shutil, "which", return_value=str(tool_bin / ("arm-none-eabi-gcc" + suffix))):
        assert sdk.find_toolchain(work, lock["version"]) == tool_bin.resolve()
    with mock.patch.object(sdk.subprocess, "check_output", return_value="14.2.1\n"):
        sdk.verify_toolchain_version(tool_bin, lock["version"])
    with mock.patch.object(sdk.subprocess, "check_output", return_value="13.3.1\n"):
        failed(lambda: sdk.verify_toolchain_version(tool_bin, lock["version"]), "version mismatch")
    cached = work / ".build/toolchains" / ("xpack-arm-none-eabi-gcc-" + lock["version"])
    shutil.copytree(tool_root, cached)
    with mock.patch.dict(os.environ, {"MK61_GCC_TOOLCHAIN": ""}), mock.patch.object(sdk.shutil, "which", side_effect=AssertionError("cache must precede PATH")):
        assert sdk.find_toolchain(work, lock["version"]) == (cached / "bin").resolve()
    (tool_bin / ("arm-none-eabi-g++" + suffix)).unlink()
    failed(lambda: sdk.toolchain_bin(tool_root), "GNU Arm tool not found")
    for path in ("/x/Arduino15/packages/s.h", r"C:\Users\a\AppData\Local\Arduino15\packages\x.h", "/x/.arduino15/core.h", "/x/cores/arduino/a.c", "/x/libraries/SrcWrapper/x.c"):
        failed(lambda p=path: gate.check_paths([p]), "Installed Arduino package")
    gate.check_paths([str(original / "device/include/stm32f411xe.h"), "-DARDUINO=10607"])

    # Exercise the actual PowerShell installer without a network request.
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if pwsh:
        bad = work / "corrupt.tar.gz"; bad.write_bytes(b"invalid archive")
        install = work / "install"
        result = subprocess.run([pwsh, "-NoLogo", "-NoProfile", "-File", str(ROOT / "tools/install_gcc_dependencies.ps1"), "-InstallRoot", str(install), "-ArchivePath", str(bad)], capture_output=True, text=True)
        assert result.returncode != 0 and "checksum mismatch" in result.stdout + result.stderr, result.stdout + result.stderr
        assert not list(install.glob(".install-*")) and not list(install.glob("xpack-*"))
print("Native SDK: exact manifest/licenses, corruption/missing/traversal, Unicode/spaces, no home/Core discovery, tool precedence, header-path gate, autocrlf Git checkout and corrupt installer rollback PASS")
