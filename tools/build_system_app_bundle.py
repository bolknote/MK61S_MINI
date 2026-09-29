#!/usr/bin/env python3
"""Build the canonical /System directory with the unified current APP ABI."""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from m8_codec import decode as decode_m8


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = (
    "FOCAL.APP", "BASIC.APP", "WBMP.APP", "MARKDOWN.APP", "CHIP8.APP",
    "SETUP.APP", "USBDISK.APP", "EXPLORER.APP", "HELP0.TXT", "HELP1.TXT",
)
MODULES = (
    ("setup", "SETUP.APP", "setup"),
    ("focal", "FOCAL.APP", "focal"),
    ("basic", "BASIC.APP", "tinybasic"),
    ("wbmp", "WBMP.APP", "wbmp-viewer"),
    ("markdown", "MARKDOWN.APP", "markdown-viewer"),
    ("chip8", "CHIP8.APP", "chip8"),
    ("usbdisk", "USBDISK.APP", "usbdisk"),
    ("explorer", "EXPLORER.APP", "explorer"),
)


def app_variant(system: str, args: argparse.Namespace) -> str:
    parts = ["ui-fonts" if args.ui_fonts else "plain"]
    if system == "markdown-viewer":
        parts.append("graphics" if args.graphics else "text")
    if system in ("focal", "tinybasic"):
        parts.append("float" if args.local_float_math else "core")
    return "+".join(parts)


def read_catalog(catalog: Path) -> dict:
    manifest_path = catalog / "catalog.json"
    if not manifest_path.exists():
        return {"format": 1, "abi": 6, "apps": []}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid APP catalog: {manifest_path}: {error}")
    if manifest.get("format") != 1 or manifest.get("abi") != 6 or \
            not isinstance(manifest.get("apps"), list):
        raise ValueError(f"unsupported APP catalog: {manifest_path}")
    return manifest


def catalog_source_key(args: argparse.Namespace, toolchain: Path) -> str:
    """Fingerprint every input that may change a portable System APP."""
    digest = hashlib.sha256()
    inputs: list[Path] = []
    build_suffixes = {
        ".S", ".c", ".cpp", ".def", ".h", ".hpp", ".inc", ".ino",
        ".json", ".ld", ".py", ".rs", ".sh",
    }
    for directory in (ROOT / "code", ROOT / "sdk/portable",
                      ROOT / "tools/.mk61-app"):
        inputs += [path for path in directory.rglob("*") if path.is_file() and
                   "__pycache__" not in path.parts and
                   path.suffix in build_suffixes]
    inputs += [Path(__file__).resolve(),
               ROOT / "tools/build_portable_app.py",
               ROOT / "tools/build_mk61_module_pack.sh"]
    for path in sorted(set(inputs), key=lambda item: item.as_posix()):
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(struct.pack("<I", len(relative)))
        digest.update(relative)
        digest.update(struct.pack("<Q", len(payload)))
        digest.update(payload)

    suffix = ".exe" if os.name == "nt" else ""
    compiler = toolchain / ("arm-none-eabi-gcc" + suffix)
    version_result = subprocess.run(
        [str(compiler), "--version"], capture_output=True, text=True)
    if version_result.returncode or not version_result.stdout:
        raise ValueError(f"cannot identify ARM compiler: {compiler}")
    digest.update(version_result.stdout.splitlines()[0].encode("utf-8"))
    digest.update(os.name.encode("ascii"))

    configured_packer = args.packer
    if configured_packer is None and os.environ.get("MK61_MODULE_PACK_BIN"):
        configured_packer = Path(os.environ["MK61_MODULE_PACK_BIN"])
    if configured_packer is not None:
        packer = configured_packer.resolve()
        if not packer.is_file():
            raise ValueError(f"APP packer not found: {packer}")
        digest.update(hashlib.sha256(packer.read_bytes()).digest())
    return digest.hexdigest()


def app_build_key(source_key: str, filename: str, system: str,
                  args: argparse.Namespace) -> str:
    identity = "\0".join((source_key, filename, system,
                           app_variant(system, args)))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def cached_catalog_app(filename: str, system: str, build_key: str,
                       args: argparse.Namespace) -> Path | None:
    catalog = args.catalog_dir.resolve()
    manifest = read_catalog(catalog)
    variant = app_variant(system, args)
    for record in manifest["apps"]:
        if record.get("name") != filename or \
                record.get("variant") != variant or \
                record.get("build_key") != build_key:
            continue
        digest = record.get("sha256", "")
        relative = record.get("path", "")
        if not isinstance(digest, str) or len(digest) != 64 or \
                relative != f"objects/{digest}.APP":
            raise ValueError(f"invalid APP catalog record: {filename}")
        stored = catalog / relative
        if not stored.is_file():
            raise ValueError(f"APP catalog object is missing: {stored}")
        payload = stored.read_bytes()
        if hashlib.sha256(payload).hexdigest() != digest or \
                len(payload) != record.get("size"):
            raise ValueError(f"APP catalog object is corrupted: {stored}")
        if len(payload) < 64 or payload[:8] != b"MK61APP\0" or \
                struct.unpack_from("<H", payload, 12)[0] != 6:
            raise ValueError(f"APP catalog object has invalid ABI: {stored}")
        return stored
    return None


def publish_catalog(source: Path, filename: str, system: str,
                    build_key: str, args: argparse.Namespace) -> Path:
    catalog = args.catalog_dir.resolve()
    objects = catalog / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    payload = source.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    stored = objects / (digest + ".APP")
    if stored.exists():
        if stored.read_bytes() != payload:
            raise ValueError(f"APP catalog hash collision: {stored}")
    else:
        temporary = objects / (stored.name + ".tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, stored)

    manifest_path = catalog / "catalog.json"
    manifest = read_catalog(catalog)

    variant = app_variant(system, args)
    record = {
        "name": filename,
        "system": system,
        "variant": variant,
        "build_key": build_key,
        "sha256": digest,
        "size": len(payload),
        "path": f"objects/{stored.name}",
    }
    records = [item for item in manifest.get("apps", [])
               if not (item.get("name") == filename and
                       item.get("variant") == variant)]
    records.append(record)
    records.sort(key=lambda item: (item["name"], item["variant"]))
    manifest["apps"] = records
    temporary_manifest = catalog / "catalog.json.tmp"
    temporary_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    os.replace(temporary_manifest, manifest_path)

    referenced = {item["path"] for item in records}
    for candidate in objects.glob("*.APP"):
        relative = f"objects/{candidate.name}"
        if relative not in referenced:
            candidate.unlink()
    return stored


def run(command: list[str | Path]) -> None:
    result = subprocess.run([str(item) for item in command])
    if result.returncode:
        raise RuntimeError(
            f"{Path(str(command[0])).name} failed with exit code "
            f"{result.returncode}")


def compiler_from_database(path: Path) -> Path:
    entries = json.loads(path.read_text(encoding="utf-8"))
    for entry in entries:
        arguments = entry.get("arguments")
        if arguments:
            candidate = str(arguments[0])
        else:
            command = entry.get("command", "")
            parts = shlex.split(command, posix=os.name != "nt") if command else []
            candidate = parts[0].strip('"') if parts else ""
        resolved = shutil.which(candidate) or candidate
        if resolved and Path(resolved).is_file():
            return Path(resolved).resolve()
    raise ValueError("ARM compiler is missing from compile_commands.json")


def boolean(value: str) -> bool:
    if value not in ("0", "1"):
        raise argparse.ArgumentTypeError("expected 0 or 1")
    return value == "1"


def prepare_usb_text_resources(stage: Path) -> None:
    # The ELF metadata is M8 because C6 and the terminal use M8 internally.
    # /System in a distribution bundle is copied through the USB FAT volume,
    # whose text-file boundary is UTF-8. C6 converts it back to M8 on eject.
    for name in ("HELP0.TXT", "HELP1.TXT"):
        path = stage / name
        path.write_bytes(decode_m8(path.read_bytes()).encode("utf-8"))


def build(args: argparse.Namespace) -> dict:
    resident = args.resident_elf.resolve()
    if not resident.is_file():
        raise ValueError(f"resident ELF not found: {resident}")
    if args.arm_toolchain_bin:
        toolchain = args.arm_toolchain_bin.resolve()
    else:
        if not args.compile_commands:
            raise ValueError("provide --compile-commands or --arm-toolchain-bin")
        database = args.compile_commands.resolve()
        if not database.is_file():
            raise ValueError(f"compile database not found: {database}")
        toolchain = compiler_from_database(database).parent
    suffix = ".exe" if os.name == "nt" else ""
    if not (toolchain / ("arm-none-eabi-gcc" + suffix)).is_file():
        raise ValueError(f"ARM GCC toolchain not found in: {toolchain}")

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    enabled = {
        "setup": args.setup,
        "focal": args.focal,
        "basic": args.basic,
        "wbmp": args.wbmp and not args.markdown,
        "markdown": args.markdown,
        "chip8": args.chip8,
        "usbdisk": args.usbdisk,
        "explorer": args.explorer,
    }
    built: list[str] = []
    catalog_hits: list[str] = []
    source_key = (catalog_source_key(args, toolchain)
                  if args.catalog_dir else None)
    with tempfile.TemporaryDirectory(prefix="mk61-system-app-") as temporary:
        work = Path(temporary)
        stage = work / "System"
        stage.mkdir()
        for key, filename, system in MODULES:
            if not enabled[key]:
                continue
            build_key = (app_build_key(source_key, filename, system, args)
                         if source_key else None)
            source = (cached_catalog_app(filename, system, build_key, args)
                      if build_key else None)
            command: list[str | Path] = [
                sys.executable, ROOT / "tools/build_portable_app.py",
                "--system", system,
                "--arm-toolchain-bin", toolchain,
                "--output-dir", work / key,
            ]
            if args.packer:
                command += ["--packer", args.packer.resolve()]
            if not args.ui_fonts:
                command.append("--no-ui-fonts")
            if system == "markdown-viewer" and not args.graphics:
                command.append("--text-only")
            if args.local_float_math and system in ("focal", "tinybasic"):
                command.append("--local-float-math")
            if source is None:
                run(command)
                source = work / key / filename
                if build_key:
                    source = publish_catalog(
                        source, filename, system, build_key, args)
            else:
                catalog_hits.append(filename)
            shutil.copy2(source, stage / filename)
            built.append(filename)

        run([sys.executable, ROOT / "tools/.mk61-app/build_terminal_help.py",
             "--resident-elf", resident, "--output-dir", stage])
        prepare_usb_text_resources(stage)
        built += ["HELP0.TXT", "HELP1.TXT"]

        # Replace only files owned by this builder. Other /System files, if
        # any, belong to the caller and are deliberately left untouched.
        for filename in CANONICAL:
            destination = output / filename
            source = stage / filename
            if source.is_file():
                temporary_file = output / (filename + ".tmp")
                shutil.copy2(source, temporary_file)
                os.replace(temporary_file, destination)
            elif destination.exists():
                destination.unlink()

    result = {
        "abi": 6,
        "resident": str(resident),
        "output": str(output),
        "apps": built,
        "graphics": args.graphics,
        "ui_fonts": args.ui_fonts,
        "local_float_math": args.local_float_math,
        "catalog": str(args.catalog_dir.resolve()) if args.catalog_dir else None,
        "catalog_hits": catalog_hits,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resident-elf", type=Path, required=True)
    parser.add_argument("--compile-commands", type=Path)
    parser.add_argument("--arm-toolchain-bin", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--packer", type=Path)
    parser.add_argument("--catalog-dir", type=Path,
                        help="shared content-addressed ABI 6 APP catalog")
    parser.add_argument("--graphics", type=boolean, default=True)
    parser.add_argument("--setup", type=boolean, default=True,
                        help="build SETUP.APP (0 when setup is resident on F411)")
    parser.add_argument("--usbdisk", type=boolean, default=True,
                        help="build USBDISK.APP (0 when USB disk is resident)")
    parser.add_argument("--explorer", type=boolean, default=False,
                        help="build EXPLORER.APP (0 when Explorer is resident)")
    parser.add_argument("--ui-fonts", type=boolean, default=True)
    parser.add_argument("--focal", type=boolean, default=True)
    parser.add_argument("--basic", type=boolean, default=True)
    parser.add_argument("--wbmp", type=boolean, default=True)
    parser.add_argument("--markdown", type=boolean, default=True)
    parser.add_argument("--chip8", type=boolean, default=True)
    parser.add_argument("--local-float-math", type=boolean, default=False)
    args = parser.parse_args()
    try:
        build(args)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        parser.exit(1, f"System APP build: {error}\n")


if __name__ == "__main__":
    main()
