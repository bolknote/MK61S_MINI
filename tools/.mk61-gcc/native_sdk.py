"""Pinned header SDK and GNU Arm tool discovery for native builds."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess


def validate_sdk(root):
    root = Path(root).resolve()
    manifest = root / "manifest.json"
    if not manifest.is_file():
        raise ValueError(f"Native SDK manifest is missing: {manifest}")
    data = json.loads(manifest.read_text())
    if data.get("schema") != 1 or len(data.get("files", {})) < 10:
        raise ValueError("Unsupported or incomplete native SDK manifest")
    for name, expected in data["files"].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name:
            raise ValueError(f"Invalid native SDK file path: {name}")
        path = root.joinpath(*relative.parts)
        if not path.is_file():
            raise ValueError(f"Native SDK file is missing: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Native SDK checksum mismatch: {name}")
    return root


def toolchain_bin(path):
    path = Path(path).resolve()
    suffix = ".exe" if os.name == "nt" else ""
    if not (path / ("arm-none-eabi-gcc" + suffix)).is_file():
        path /= "bin"
    for name in ("gcc", "g++", "ar", "ranlib", "objcopy", "size", "nm", "objdump", "c++filt"):
        if not (path / ("arm-none-eabi-" + name + suffix)).is_file():
            raise ValueError(f"GNU Arm tool not found: {path}/arm-none-eabi-{name}{suffix}")
    return path


def find_toolchain(project, version, explicit=None):
    # No dependency on an Arduino installation, registry or board package.
    selected = explicit or os.environ.get("MK61_GCC_TOOLCHAIN")
    if selected:
        return toolchain_bin(selected)
    cached = Path(project) / ".build/toolchains" / ("xpack-arm-none-eabi-gcc-" + version)
    if cached.is_dir():
        return toolchain_bin(cached)
    executable = shutil.which("arm-none-eabi-gcc")
    if executable:
        return toolchain_bin(Path(executable).parent)
    raise ValueError("GNU Arm GCC is missing; run tools/install_gcc_dependencies.ps1, "
                     "put arm-none-eabi-gcc on PATH or set MK61_GCC_TOOLCHAIN")


def verify_toolchain_version(tool_bin, version):
    suffix = ".exe" if os.name == "nt" else ""
    compiler = Path(tool_bin) / ("arm-none-eabi-gcc" + suffix)
    actual = subprocess.check_output([str(compiler), "-dumpfullversion"], text=True).strip()
    expected = version.split("-", 1)[0]
    if actual != expected:
        raise ValueError(f"GNU Arm version mismatch: expected {expected}, found {actual}")
