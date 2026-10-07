#!/usr/bin/env python3
"""Build the canonical /System directory with the unified current APP ABI."""

import argparse
from contextlib import contextmanager
import errno
import hashlib
import json
import os
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from m8_codec import decode as decode_m8


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = (
    "FOCAL.APP", "BASIC.APP", "WBMP.APP", "MARKDOWN.APP", "CHIP8.APP",
    "SETUP.APP", "USBDISK.APP", "EXPLORER.APP", "HELP0.TXT", "HELP1.TXT",
    "LANGVM.APP", "LANGIN.APP",
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
    ("language-vm", "LANGVM.APP", "language-vm"),
    ("language-input", "LANGIN.APP", "language-input"),
)
CATALOG_LOCK_TIMEOUT_SECONDS = 120.0


def empty_catalog() -> dict:
    return {"format": 1, "abi": 6, "apps": []}


def atomic_write(path: Path, payload: bytes) -> None:
    """Replace *path* with a complete same-directory temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
                prefix=f".{path.name}.", suffix=".tmp",
                dir=path.parent, delete=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
            temporary = Path(stream.name)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


@contextmanager
def catalog_lock(catalog: Path):
    """Serialize manifest/object publication across Arduino IDE processes."""
    catalog.mkdir(parents=True, exist_ok=True)
    lock_path = catalog / ".catalog.lock"
    stream = lock_path.open("a+b")
    locked = False
    try:
        # Windows byte-range locks require the byte to exist. Two creators may
        # write the same sentinel concurrently; both writes are harmless.
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + CATALOG_LOCK_TIMEOUT_SECONDS
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if error.errno not in (errno.EACCES, errno.EAGAIN,
                                            errno.EDEADLK):
                        raise
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"timed out waiting for APP catalog lock: "
                            f"{lock_path}") from error
                    time.sleep(0.05)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        locked = True
        yield
    finally:
        if locked:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def write_catalog(catalog: Path, manifest: dict) -> None:
    payload = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8")
    atomic_write(catalog / "catalog.json", payload)


def system_app_workspace(output: Path):
    """Keep ARM GCC outputs under Arduino's already-vetted build path."""
    return tempfile.TemporaryDirectory(
        prefix=".mk61-system-app-", dir=output.resolve().parent)


def app_variant(system: str, args: argparse.Namespace) -> str:
    parts = ["ui-fonts" if args.ui_fonts else "plain"]
    if system == "markdown-viewer":
        parts.append("graphics" if args.graphics else "text")
    if system in ("focal", "tinybasic"):
        parts.append("vm-compiler-v5-flow-compact1-specialized" if getattr(args,"language_vm_compiler",False)
                     else "float" if args.local_float_math else "core")
    if system == "language-vm":
        parts += ["split-v6-flow1-compact1", "float" if args.local_float_math else "core"]
    if system == "language-input":
        parts.append("cold-v6-flow1-compact1")
    return "+".join(parts)


def read_catalog(catalog: Path) -> dict:
    manifest_path = catalog / "catalog.json"
    if not manifest_path.exists():
        return empty_catalog()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid APP catalog: {manifest_path}: {error}")
    if not isinstance(manifest, dict) or manifest.get("format") != 1 or \
            manifest.get("abi") != 6 or \
            not isinstance(manifest.get("apps"), list):
        raise ValueError(f"unsupported APP catalog: {manifest_path}")
    for record in manifest["apps"]:
        if not isinstance(record, dict) or not all(
                isinstance(record.get(field), str)
                for field in ("name", "system", "variant", "build_key",
                              "sha256", "path")) or \
                not isinstance(record.get("size"), int):
            raise ValueError(f"invalid APP catalog record: {manifest_path}")
    return manifest


def catalog_source_inputs() -> list[Path]:
    """Return every source and policy file that can accept/reject an APP."""
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
               ROOT / "tools/build_mk61_module_pack.sh",
               ROOT / "tests/analyze_stack_usage.py",
               ROOT / "tests/check_stack_usage.py"]
    return sorted(set(inputs), key=lambda item: item.as_posix())


def catalog_source_key(args: argparse.Namespace, toolchain: Path) -> str:
    """Fingerprint every input that may change a portable System APP."""
    digest = hashlib.sha256()
    for path in catalog_source_inputs():
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


def cached_catalog_payload(filename: str, system: str, build_key: str,
                           args: argparse.Namespace) -> bytes | None:
    catalog = args.catalog_dir.resolve()
    with catalog_lock(catalog):
        try:
            manifest = read_catalog(catalog)
        except (OSError, ValueError) as error:
            print(f"System APP cache ignored and will be rebuilt: {error}",
                  file=sys.stderr)
            try:
                (catalog / "catalog.json").unlink()
            except FileNotFoundError:
                pass
            return None
        variant = app_variant(system, args)
        for record in manifest["apps"]:
            if record.get("name") != filename or \
                    record.get("variant") != variant or \
                    record.get("build_key") != build_key:
                continue
            try:
                digest = record.get("sha256", "")
                relative = record.get("path", "")
                if len(digest) != 64 or relative != f"objects/{digest}.APP":
                    raise ValueError(
                        f"invalid APP catalog record: {filename}")
                stored = catalog / relative
                if not stored.is_file():
                    raise ValueError(
                        f"APP catalog object is missing: {stored}")
                payload = stored.read_bytes()
                if hashlib.sha256(payload).hexdigest() != digest or \
                        len(payload) != record.get("size"):
                    raise ValueError(
                        f"APP catalog object is corrupted: {stored}")
                if len(payload) < 64 or payload[:8] != b"MK61APP\0" or \
                        struct.unpack_from("<H", payload, 12)[0] != 6:
                    raise ValueError(
                        f"APP catalog object has invalid ABI: {stored}")
                # Materialize the complete object while the catalog is
                # locked. A later publisher may then safely prune this
                # content-addressed file without racing this build.
                return payload
            except (OSError, ValueError) as error:
                print(f"System APP cache entry ignored and will be rebuilt: "
                      f"{error}", file=sys.stderr)
                manifest["apps"] = [item for item in manifest["apps"]
                                    if item is not record]
                write_catalog(catalog, manifest)
                return None
    return None


def publish_catalog(source: Path, filename: str, system: str,
                    build_key: str, args: argparse.Namespace) -> Path:
    catalog = args.catalog_dir.resolve()
    payload = source.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    with catalog_lock(catalog):
        objects = catalog / "objects"
        objects.mkdir(parents=True, exist_ok=True)
        stored = objects / (digest + ".APP")
        if stored.exists():
            if stored.read_bytes() != payload:
                raise ValueError(f"APP catalog hash collision: {stored}")
        else:
            atomic_write(stored, payload)

        try:
            manifest = read_catalog(catalog)
        except (OSError, ValueError) as error:
            print(f"System APP catalog was invalid and has been reset: {error}",
                  file=sys.stderr)
            manifest = empty_catalog()

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
        write_catalog(catalog, manifest)

        referenced = {item["path"] for item in records}
        for candidate in objects.glob("*.APP"):
            if f"objects/{candidate.name}" not in referenced:
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
    overlay_vm = getattr(args, "overlay_language_vm", False)
    if overlay_vm and not getattr(args, "language_vm_compiler", False):
        raise ValueError("overlay language VM requires compiler-only BASIC/FOCAL")
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
        "language-vm": overlay_vm and (args.basic or args.focal),
        "language-input": overlay_vm and (args.basic or args.focal),
    }
    built: list[str] = []
    catalog_hits: list[str] = []
    source_key = (catalog_source_key(args, toolchain)
                  if args.catalog_dir else None)
    with system_app_workspace(output) as temporary:
        work = Path(temporary)
        stage = work / "System"
        stage.mkdir()
        for key, filename, system in MODULES:
            if not enabled[key]:
                continue
            build_key = (app_build_key(source_key, filename, system, args)
                         if source_key else None)
            cached = (cached_catalog_payload(filename, system, build_key, args)
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
            if system in ("focal", "tinybasic"):
                if getattr(args,"language_vm_compiler",False):command.append("--language-vm-compiler")
                elif args.local_float_math:command.append("--local-float-math")
            if system == "language-vm":
                command.append("--split-language-vm")
                if args.local_float_math: command.append("--local-float-math")
            destination = stage / filename
            if cached is None:
                run(command)
                source = work / key / filename
                if build_key:
                    publish_catalog(source, filename, system, build_key, args)
                shutil.copy2(source, destination)
            else:
                catalog_hits.append(filename)
                destination.write_bytes(cached)
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
        "language_vm_compiler": getattr(args,"language_vm_compiler",False),
        "overlay_language_vm": overlay_vm,
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
    parser.add_argument("--language-vm-compiler", type=boolean, default=False,
                        help="compiler-only language APPs for the resident VM experiment")
    parser.add_argument("--overlay-language-vm", type=boolean, default=False,
                        help="include split hot LANGVM.APP and cold LANGIN.APP")
    args = parser.parse_args()
    try:
        build(args)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        parser.exit(1, f"System APP build: {error}\n")


if __name__ == "__main__":
    main()
