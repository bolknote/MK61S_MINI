#!/usr/bin/env python3
"""Build bounded, paged URQ packages shared by STM32 and PicoCalc."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import zlib

ROOT = Path(__file__).resolve().parents[3]
PAGE = 512
FILE_LIMIT = 60 * 1024
# Fifteen C9 data blocks fit in 60 KiB without rounding a part up to a
# sixteenth 4-KiB erase sector (each data block has a 32-byte header).
OPTIMAL_PART_LIMIT = 15 * (4096 - 32)
MODES = {"urqw": 0, "urqw1": 0, "dosurq": 1, "ripurq": 2, "akurq": 3}
_codec = None
_m8 = None


def m8(text):
    global _m8
    if _m8 is None:
        spec = importlib.util.spec_from_file_location("urq_m8", ROOT / "dev/lib/m8_codec.py")
        _m8 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_m8)
    return _m8.encode(text)


def codec():
    global _codec
    if _codec is None:
        spec = importlib.util.spec_from_file_location(
            "urq_zx0", ROOT / "tools/apps/packer/mk61_module_pack.py")
        _codec = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_codec)
    return _codec


def fold(data):
    return bytes(c + 32 if 65 <= c <= 90 or 0xC0 <= c <= 0xDF
                 else 0xB8 if c == 0xA8 else c for c in data)


def name_hash(data):
    result = 2166136261
    for c in fold(data):
        result = ((result ^ c) * 16777619) & 0xFFFFFFFF
    return result


def decode_source(data, encoding=None):
    if encoding:
        name = {"CP1251": "cp1251", "CP866": "cp866",
                "UTF-8": "utf-8-sig"}.get(encoding.upper(), encoding)
        return data.decode(name)
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    if all(byte < 128 for byte in data):
        return data.decode("ascii")
    raise ValueError("ambiguous encoding: specify --encoding UTF-8, CP1251 or CP866")


def may_change_mode(source, depth=0):
    """Prove fixed mode conservatively; computed commands/names retain comments."""
    def writable_mode(name):
        name = name.strip().lower()
        while name.startswith('inv_'):
            name = name[4:]
        return '#' in name or name == 'urq_mode'

    if depth > 24:
        return True
    source = source.strip()
    if not source or source.startswith(':'):
        return False
    if '&' in source:
        return any(may_change_mode(part, depth + 1) for part in source.split('&'))
    parts = source.split(None, 1)
    operation = parts[0].lower()
    argument = parts[1] if len(parts) == 2 else ''
    if operation == 'if':
        branches = re.split(r'\bthen\b', argument, maxsplit=1, flags=re.I)
        if len(branches) != 2:
            return True
        return any(may_change_mode(part, depth + 1)
                   for part in re.split(r'\belse\b', branches[1], flags=re.I))
    if operation in ('p', 'print', 'pln', 'println'):
        # Printed links are executable commands. Dynamic text can introduce
        # links too (including text obtained through INPUT or file_content).
        # Only literal character/space/newline tags are statically harmless.
        literal = re.sub(r'##[0-9]+\$|#/\$|#\$', '', argument)
        return '[[' in literal or '#' in literal
    if operation == 'btn':
        target, comma, _ = argument.partition(',')
        return not comma or may_change_mode(target, depth + 1)
    if operation in ('instr', 'input', 'anykey', 'inv+', 'inv-', 'invkill'):
        name = argument.split('=', 1)[0] if operation == 'instr' else argument
        if operation in ('inv+', 'inv-'):
            name = name.split(',', 1)[-1]
        if operation == 'invkill' and not name.strip():
            return True  # a restored/dynamic inventory may contain urq_mode
        return writable_mode(name)
    if '=' in source:
        name = source.split('=', 1)[0].rstrip(' \t+-*/').lower()
        return writable_mode(name)
    return '#' in operation


def normalize(text, mode, *, strip_static_comments=True, validate_lines=True):
    if "\0" in text:
        raise ValueError("NUL in source")
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    if mode == "akurq":
        def html(match):
            body = re.sub(r";[^\r\n]*", "", match.group(1))
            body = re.sub(r"[\r\n]+", " ", body).strip()
            body = re.sub(r'<a\s+href="btn:([^"]+)"\s*>\s*([^<]+?)\s*</a>',
                          r"[[\2|\1]]", body, flags=re.I)
            return "pln " + body + "\n"
        text = re.sub(r"<html>([\s\S]*?)</html>", html, text, flags=re.I)
    lines = [line.lstrip() for line in re.split(r"[\r\n]+", text.strip("\r\n"))]
    for i in range(len(lines) - 1, 0, -1):
        if lines[i].startswith("_") and not lines[i].startswith("__"):
            lines[i - 1] += lines[i][1:]
            lines[i] = ""
    # Preserve old package IDs when fixed classic mode is provable. Otherwise
    # the executor must apply comments using the mode at source-line fetch.
    if strip_static_comments and mode in ("dosurq", "ripurq", "akurq") and not any(
            may_change_mode(line.split(';', 1)[0]) for line in lines):
        lines = [line.split(";", 1)[0] for line in lines]
    if validate_lines:
        for line in lines:
            if len(m8(line)) >= 1024:
                raise ValueError("source line exceeds the 1023-M8-byte execution limit")
    return lines


def make_package(data, mode, encoding=None, manifest=None, resources=None, zx0_parser=None):
    if mode not in MODES:
        raise ValueError("unknown URQ mode")
    text = decode_source(data, encoding)
    lines = normalize(text, mode)
    # Fail unsupported execution dependencies, never silently drop game logic.
    if re.search(r"(?im)(?:^|&|\bthen\s|\belse\s)\s*javascript\b|<script\b", "\n".join(lines)):
        raise ValueError("JavaScript is outside the text profile")
    encoded = [m8(line) for line in lines]
    labels = {}
    # UrqW collects labels before Quest.next() applies dialect comments.
    label_lines = [m8(line) for line in normalize(
        text, mode, strip_static_comments=False, validate_lines=False)]
    for i in range(len(label_lines) - 1, -1, -1):
        if label_lines[i].startswith(b":"):
            name = label_lines[i][1:].strip()
            if not name or len(name) >= 128:
                raise ValueError("label must contain 1..127 M8 bytes")
            labels[fold(name)] = (fold(name), i)
    label_list = sorted(labels.values(), key=lambda x: (name_hash(x[0]), fold(x[0])))
    payload = bytearray(4 * len(lines) + 12 * len(labels))
    for i, (name, line) in enumerate(label_list):
        offset = len(payload)
        payload += name + b"\0"
        struct.pack_into("<III", payload, 4 * len(lines) + 12 * i,
                         name_hash(name), offset, line)
    for i, line in enumerate(encoded):
        struct.pack_into("<I", payload, i * 4, len(payload))
        payload += line + b"\0"
    metadata_offset = len(payload)
    first = min(labels.values(), key=lambda entry: entry[1])[0] if labels else b""
    metadata = manifest or {}
    for value in (first, m8(metadata.get("urqw_title", "")),
                  m8(metadata.get("urqw_game_lang", "")), m8(metadata.get("urqw_game_ifid", ""))):
        if len(value) >= 256:
            raise ValueError("metadata exceeds 255 M8 bytes")
        payload += value + b"\0"
    if not payload:
        raise ValueError("empty source")
    flags = int(bool(metadata.get("html_support", mode in ("urqw", "urqw1", "akurq"))))
    if resources:
        flags |= 2
        payload += struct.pack('<H',len(resources))
        table=len(payload);payload+=bytes(8*len(resources))
        for index,(name,content) in enumerate(sorted(resources.items())):
            path=m8(name.strip().replace('\\','/').lstrip('/'));text=m8(content)
            if not path or len(path)>=128 or len(text)>=1024 or b'\0' in path+text:
                raise ValueError('text resource exceeds name/content limits or contains NUL')
            name_at=len(payload);payload+=path+b'\0';text_at=len(payload);payload+=text+b'\0'
            struct.pack_into('<II',payload,table+index*8,name_at,text_at)
    identity = hashlib.sha256(bytes([MODES[mode], flags]) + payload).digest()[:16]
    parser = zx0_parser or metadata.get('mk61_zx0_parser', 'greedy')
    if parser not in ('greedy', 'optimal'):
        raise ValueError('unknown ZX0 parser')
    pages = None
    if parser == 'optimal':
        spec = importlib.util.spec_from_file_location(
            'urq_page_compression', Path(__file__).with_name('page_compression.py'))
        optimizer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(optimizer)
        pages = optimizer.optimal_pages(payload)
    parts = [bytearray(32)]
    part_limit = OPTIMAL_PART_LIMIT if parser == 'optimal' else FILE_LIMIT
    directory = bytearray()
    for offset in range(0, len(payload), PAGE):
        raw = bytes(payload[offset:offset + PAGE])
        packed = pages[offset // PAGE] if pages is not None else codec().zx0_encode(raw)
        if (codec().zx0_decode(packed, len(raw)) if pages is None or len(packed) < len(raw) else packed) != raw:
            raise ValueError("ZX0 self-check failed")
        if len(packed) >= len(raw):
            packed = raw
        if len(parts[-1]) + len(packed) > part_limit:
            parts.append(bytearray(32))
        at = len(parts[-1])
        directory += struct.pack("<HHHHII", len(parts) - 1, at, len(packed),
                                 len(raw), zlib.crc32(raw), zlib.crc32(packed))
        parts[-1] += packed
    if len(directory) + 64 > FILE_LIMIT:
        raise ValueError("page directory exceeds 60 KiB")
    for i, part in enumerate(parts):
        part[:32] = struct.pack("<4sHH16sII", b"URQD", 1, i, identity,
                                zlib.crc32(part[32:]), len(part) - 32)
    header = struct.pack("<8sHBBIIIIIIIHH16s", b"MK61URQ\0", 1, MODES[mode], flags,
                         len(payload), len(lines), len(labels), 0, 4 * len(lines),
                         metadata_offset, len(directory) // 16, len(parts), PAGE, identity)
    assert len(header) == 60
    main = header + struct.pack("<I", zlib.crc32(header)) + directory
    result = {"game.urq": main}
    result.update({f"p{i:04d}.uqd": bytes(part) for i, part in enumerate(parts)})
    report = {"format": 1, "mode": mode, "id": identity.hex(),
              "source_sha256": hashlib.sha256(data).hexdigest(),
              "logical_bytes": len(payload), "lines": len(lines),
              "labels": len(labels), "parts": len(parts),
              "stored_bytes": sum(map(len, result.values())),
              "title": (manifest or {}).get("urqw_title", "")}
    report["ifid"] = metadata.get("urqw_game_ifid", "")
    report['text_resources']=len(resources or {})
    if parser == 'optimal':
        report['zx0_parser'] = parser
    return result, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--encoding")
    parser.add_argument('--zx0-parser', choices=('greedy', 'optimal'),
                        help='optimal uses a host C compiler; the game format and memory use are unchanged')
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--text-resource",action='append',default=[],metavar='NAME=PATH',
                        help='Include a UTF-8 text resource for file_content/file_url')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text()) if args.manifest else {}
    mode = args.mode or manifest.get("urq_mode") or ("urqw" if args.manifest else None)
    if not mode:
        parser.error("--mode is required without manifest urq_mode")
    try:
        resources={}
        for value in args.text_resource:
            name,path=value.split('=',1);resources[name]=Path(path).read_bytes().decode('utf-8-sig')
        files, report = make_package(args.source.read_bytes(), mode,
                                    args.encoding or manifest.get("game_encoding"), manifest,resources,args.zx0_parser)
    except (ValueError, UnicodeError) as exc:
        parser.error(str(exc))
    args.output.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (args.output / name).write_bytes(data)
    (args.output / "package.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
