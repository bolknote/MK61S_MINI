"""Select and synchronize the reviewed programs collection for a concrete build."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import struct
import subprocess
import tempfile
import zlib

from m8_codec import encode as m8_encode, decode as m8_decode

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = '/System/PROGRAMS.TXT'
TEXT = {'.m61', '.foc', '.tbi', '.txt', '.md'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def logical(data, name):
    # Hash the bytes represented by a text file on the device, independently
    # of its host UTF-8/M8 representation and BOM.
    if PurePosixPath(name).suffix.lower() in TEXT:
        text = data.decode('utf-8-sig')
        return m8_decode(m8_encode(text)).encode('utf-8')
    return data


def safe_path(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or any(c in name for c in '\\\t\r\n\0"')
            or '..' in path.parts or str(path) != name or name.startswith('.')):
        raise ValueError('unsafe bundle path: ' + name)
    return path


def firmware_identity(data):
    candidates = []
    for match in re.finditer(b'MK61FWC\0', data):
        offset = match.start()
        if offset + 40 > len(data):
            continue
        magic, version, size, base, length, crc, build, profile, flags, reserved = struct.unpack_from('<8sHH7I', data, offset)
        if version == 1 and size == 40 and length == len(data) and crc == build and build and flags == 1 and reserved == 0:
            zeroed = data[:offset+20] + bytes(8) + data[offset+28:]
            if zlib.crc32(zeroed) == crc:
                candidates.append(f'{build:08X}')
    if len(candidates) != 1:
        raise ValueError('a uniquely sealed firmware image is required')
    return candidates[0]


def capabilities(flags, profile, mcu, firmware):
    schema = json.loads((Path(__file__).with_name('program-capabilities.json')).read_text())
    definitions = dict((m.group(1), m.group(2) or '1') for m in re.finditer(r'(?:^|\s)-D(\w+)(?:=([^\s]+))?', flags))
    def bit(name):
        value = definitions.get(name)
        if value not in ('0', '1'):
            raise ValueError('missing/ambiguous final build definition: ' + name)
        return value == '1'
    features = {key: bit(name) for key, name in schema['features'].items()}
    features['graphics'] = features['usb_screen'] or any(name in definitions for name in schema['graphics_defines'])
    features['bitmap'] = features['graphics'] or (definitions.get('MK61_OLED1602_WS0010') == '1' and definitions.get('MK61_WS0010_GRAPHICS_100X16') == '1')
    features.update(apps=True, s1=True, math=features['focal'] or features['basic'])
    features['urq'] = (firmware.parent/'Apps/URQ.APP').is_file() and (firmware.parent/'Apps/URQUI.APP').is_file()
    required = {}
    for feature, (placement, name) in schema['system_apps'].items():
        if features[feature] and bit(placement) and not (feature == 'wbmp' and features['markdown']):
            required[feature] = name
    image = firmware.read_bytes()
    identity = profile + '-uc1609' if profile.startswith('classic-') or profile == '40th' else profile
    return dict(format=1, platform='stm32', mcu=mcu, profile=profile,
                device_profile=identity, build_id=firmware_identity(image), abi=schema['abi'],
                firmware=firmware.name, firmware_sha256=sha(image), features=features,
                system_apps=required, app_memory_limit=20480)


def pico_capabilities(metadata, binary, features):
    return dict(format=1, platform='picocalc', mcu='rp2040', profile='picocalc-pico-h',
                device_profile='picocalc-pico-h', build_id=metadata['build_id'].upper(), abi=6,
                firmware=binary.name, firmware_sha256=sha(binary.read_bytes()),
                features=features, system_apps={}, app_memory_limit=49152)


def resolved_build_flags(database):
    entries = json.loads(database.read_text())
    entry = next((e for e in entries if str(e['file']).endswith('/terminal.cpp')), None)
    if entry is None:
        entry = next(e for e in entries if str(e['file']).endswith('/script_runtime.cpp'))
    command = entry.get('arguments') or shlex.split(entry['command'])
    args, skip = [], False
    for arg in command[1:]:
        if skip:
            skip = False
        elif arg in ('-o', '-MF', '-MT', '-MQ'):
            skip = True
        elif arg not in ('-c', '-MD', '-MMD', '-MP', entry['file']):
            args.append(arg)
    schema = json.loads(Path(__file__).with_name('program-capabilities.json').read_text())
    names = set(schema['features'].values()) | {v[0] for v in schema['system_apps'].values()}
    expressions = {name: name for name in names}
    expressions.update(MK61_DISPLAY_UC1609='MK61_HAS_COMPILED_GRAPHICS',
                       MK61_OLED1602_WS0010='defined(MK61_OLED1602_WS0010)',
                       MK61_WS0010_GRAPHICS_100X16='MK61_WS0010_GRAPHICS_100X16')
    source = '#include "config.h"\n' + ''.join(f'#if {expr}\nBUNDLE_{name} 1\n#else\nBUNDLE_{name} 0\n#endif\n' for name, expr in expressions.items())
    run = subprocess.run([command[0], *args, '-E', '-P', '-x', 'c++', '-'], input=source,
                         cwd=entry['directory'], text=True, capture_output=True, check=True)
    found = dict(re.findall(r'^BUNDLE_(\w+) ([01])$', run.stdout, re.M))
    if found.keys() != expressions.keys():
        raise ValueError('cannot resolve actual build capabilities')
    # Undefined hardware macros must remain absent, not defined to zero.
    return ' '.join('-D' + name + '=' + value for name, value in found.items()
                    if name not in ('MK61_DISPLAY_UC1609', 'MK61_OLED1602_WS0010') or value == '1')


def compiled_pico_features(database):
    entries = json.loads(database.read_text())
    entry = next(e for e in entries if str(e['file']).endswith('/script_runtime.cpp'))
    command = entry.get('arguments') or shlex.split(entry['command'])
    flags = ' '.join(arg for arg in command if arg.startswith('-D'))
    schema = json.loads(Path(__file__).with_name('program-capabilities.json').read_text())
    values = dict(re.findall(r'-D(\w+)=([01])', flags))
    features = {key: values[name] == '1' for key, name in schema['features'].items()}
    features.update(graphics=True, bitmap=True, apps=True, s1=True, math=True,urq=True)
    return features


def file_limit(cap, extension):
    pico = cap['platform'] == 'picocalc'
    return {'.m61':1536, '.txt':1536, '.md':1536, '.bin':4096,
            '.urq':61440, '.uqd':61440, '.urs':61440,
            '.tbi':65534, '.foc':65534, '.mks':2048, '.ch8':3584,
            '.fmk':1536 if cap['mcu'] == 'f401' else 8192,
            '.wbmp':16384 if pico else 1600,
            '.app':cap['app_memory_limit'] + 64}[extension]


def wire_size(data, name):
    return len(m8_encode(data.decode('utf-8-sig'))) if PurePosixPath(name).suffix.lower() in TEXT else len(data)


def load_capabilities(bundle):
    cap = json.loads((bundle / 'program-capabilities.json').read_text())
    if (cap.get('format') != 1 or cap.get('platform') not in ('stm32', 'picocalc') or cap.get('abi') != 6
            or not re.fullmatch('[0-9A-Fa-f]{8}', cap.get('build_id', ''))):
        raise ValueError('unsupported program capabilities; rebuild the firmware bundle')
    safe_path(cap['firmware'])
    if sha((bundle / cap['firmware']).read_bytes()) != cap['firmware_sha256']:
        raise ValueError('capabilities belong to another firmware image')
    for value in cap['features'].values():
        if type(value) is not bool:
            raise ValueError('capabilities must contain boolean feature values')
    return cap


def validate_app(path, cap):
    data = path.read_bytes()
    if (len(data) < 64 or data[:8] != b'MK61APP\0' or struct.unpack_from('<HHH', data, 8) != (1, 64, cap['abi'])
            or data[14] != 4 or data[15] not in (0, 1)):
        raise ValueError(str(path) + ': incompatible application ABI/header')
    flags, base, stored, image, memory, entry = struct.unpack_from('<6I', data, 16)
    pico = cap['platform'] == 'picocalc'
    if (bool(flags & 8) != pico or flags & ~(31 if pico else 7) or not flags & 4 or base != 0x20000000
            or not 0 < image <= memory <= cap['app_memory_limit'] or entry >= image
            or len(data) != 64 + stored or zlib.crc32(data[:60]) != struct.unpack_from('<I', data, 60)[0]
            or zlib.crc32(data[64:]) != struct.unpack_from('<I', data, 48)[0]):
        raise ValueError(str(path) + ': incompatible CPU, memory bounds or checksum')
    return data


def frozen_plan(directory, cap):
    manifest = json.loads((directory/'programs-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 1 or manifest.get('capabilities') != cap or not isinstance(manifest.get('files'), list):
        raise ValueError('program manifest belongs to another firmware bundle')
    records, names = [], set()
    for record in manifest['files']:
        name = record['path']
        path = safe_path(name)
        if path.parts[0] not in ('app','apps','games','library','examples','sheets','urq','CHIP8','Fonts'):
            raise ValueError('unexpected distribution destination: ' + name)
        source = directory/name
        if source.is_symlink() or not source.resolve().is_relative_to(directory.resolve()) or not source.is_file():
            raise ValueError('missing/unsafe distribution source: ' + name)
        data = logical(source.read_bytes(), name)
        if sha(data) != record['sha256'] or wire_size(data, name) != record['size']:
            raise ValueError('distribution file checksum mismatch: ' + name)
        if source.suffix.lower() == '.app':
            validate_app(source, cap)
        if wire_size(data, name) > file_limit(cap, source.suffix.lower()):
            raise ValueError('distribution file exceeds device limit: ' + name)
        if name.casefold() in names:
            raise ValueError('case-insensitive distribution collision')
        names.add(name.casefold())
        records.append({**record, 'source':str(source.resolve())})
    for record in manifest.get('system_files', []):
        safe_path(record['path'])
        if sha((directory.parent/'System'/record['path']).read_bytes()) != record['sha256']:
            raise ValueError('distribution System dependency mismatch')
    return {**manifest, 'files':records}


def plan(bundle, root=ROOT, *, prefer_bundle=True):
    cap = load_capabilities(bundle)
    if prefer_bundle:
        if (bundle/'Programs/programs-manifest.json').exists():
            return frozen_plan(bundle/'Programs', cap)
        if cap['platform'] == 'picocalc' and (bundle/'programs-manifest.json').exists():
            return frozen_plan(bundle, cap)
    catalog = json.loads((Path(__file__).with_name('program-catalog.json')).read_text())
    features = dict(cap['features'])
    files, packages, skipped = [], [], []
    def missing(requirements):
        return [key for key in requirements if not features.get(key, False)]
    def add(source, destination, package):
        safe_path(destination)
        if source.is_symlink() or not source.is_file():
            raise ValueError('missing/unsafe package source: ' + str(source))
        raw = source.read_bytes()
        if source.suffix.lower() == '.app':
            validate_app(source, cap)
        if source.suffix.lower() == '.mks':
            if (len(raw) < 20 or raw[:5] != b'MKSH\x01' or
                    struct.unpack_from('<H', raw, 12)[0] != len(raw)-20 or
                    struct.unpack_from('<I', raw, 16)[0] != zlib.crc32(raw[:16]+raw[20:])):
                raise ValueError(str(source) + ': invalid sheet header/checksum')
        data = logical(raw, destination)
        files.append(dict(path=destination, source=str(source.resolve()), size=wire_size(data, destination), sha256=sha(data), package=package))
    for name, spec in catalog['apps'].items():
        if spec.get('platform') and spec['platform'] != cap['platform']:
            continue
        need = missing(spec['requires'])
        source = (bundle / 'apps' / (name + '.APP') if cap['platform'] == 'picocalc' else
                  bundle / 'Apps' / (name + '.APP') if spec.get('built') else root / 'programs/app' / (name + '.APP'))
        if need:
            skipped.append(dict(package='app/' + name, reason='requires ' + ', '.join(need)))
        else:
            add(source, ('apps/' if cap['platform'] == 'picocalc' else 'app/') + name + '.APP', 'app/' + name)
            packages.append('app/' + name)
    features['sheet'] = 'app/SHEET' in packages
    for folder, group in catalog['groups'].items():
        if folder == 'app':
            icon = root / 'programs/app/autoexec.wbmp'
            if packages and icon.exists() and features.get('bitmap'):
                add(icon, ('apps/' if cap['platform'] == 'picocalc' else 'app/') + 'autoexec.wbmp', 'app')
            continue
        directory = root / 'programs' / folder
        if not directory.is_dir():
            continue
        need = missing(group['requires'])
        if need:
            skipped.append(dict(package=folder, reason='requires ' + ', '.join(need)))
            continue
        units = sorted(p for p in directory.iterdir() if p.is_dir()) if folder == 'games' else [directory]
        if folder == 'games':
            root_icon = directory / 'autoexec.wbmp'
            if features.get('bitmap') and root_icon.exists():
                add(root_icon, 'games/autoexec.wbmp', 'games')
        for unit in units:
            package = unit.relative_to(root / 'programs').as_posix()
            sources = sorted(p for p in unit.rglob('*') if p.is_file() and not any(part.startswith('.') for part in p.relative_to(unit).parts))
            required = list(catalog['games'].get(unit.name, [])) if folder == 'games' else []
            # Interpreter scripts in a game form one package: never install a
            # launcher whose required BASIC/FOCAL parts were filtered out.
            if folder == 'games':
                for source in sources:
                    if source.suffix.lower() in ('.tbi', '.foc'):
                        required.extend(catalog['extensions'][source.suffix.lower()])
            need = missing(required)
            if need:
                skipped.append(dict(package=package, reason='requires ' + ', '.join(sorted(set(need)))))
                continue
            count = 0
            for source in sources:
                ext = source.suffix.lower()
                if ext not in catalog['extensions']:
                    continue
                need = missing(catalog['extensions'][ext])
                if need:
                    skipped.append(dict(package=source.relative_to(root/'programs').as_posix(), reason='requires ' + ', '.join(need)))
                    continue
                if cap['platform'] == 'stm32' and (source.stem.endswith('-320') or source.name.endswith('320.FMK')):
                    continue
                size = wire_size(logical(source.read_bytes(), source.name), source.name)
                limit = file_limit(cap, ext)
                if size > limit:
                    skipped.append(dict(package=source.relative_to(root/'programs').as_posix(), reason=f'{size} bytes exceeds {cap["mcu"]} file limit {limit}'))
                    continue
                add(source, source.relative_to(root / 'programs').as_posix(), package)
                count += 1
            if folder == 'Fonts' and not any(f['package'] == package and f['path'].lower().endswith('.fmk') for f in files):
                files[:] = [f for f in files if f['package'] != package]
                count = 0
            if count:
                packages.append(package)
    for directory in sorted((root / 'programs').iterdir()):
        if directory.is_dir() and directory.name not in catalog['groups']:
            skipped.append(dict(package=directory.name, reason='not in the reviewed program catalog'))
    paths = [f['path'].casefold() for f in files]
    if len(paths) != len(set(paths)):
        raise ValueError('case-insensitive destination collision')
    # Only modules required by the selected files must be present.
    used = set()
    for record in files:
        ext = PurePosixPath(record['path']).suffix.lower()
        used.update(catalog['extensions'].get(ext, []))
        if record['path'].endswith('/SHEET.APP'):
            used.update(('focal', 'basic'))
    for feature in used:
        module = cap.get('system_apps', {}).get(feature)
        if module and not (bundle / 'System' / module).is_file():
            raise ValueError('incomplete firmware bundle: missing System/' + module)
    system_files = [dict(path=p.relative_to(bundle/'System').as_posix(), sha256=sha(p.read_bytes()))
                    for p in sorted((bundle/'System').rglob('*.APP'))] if (bundle/'System').is_dir() else []
    return dict(format=1, capabilities=cap, packages=packages, skipped=skipped, files=files,
                system_files=system_files, total_bytes=sum(f['size'] for f in files))


def display(selection):
    cap = selection['capabilities']
    print(f"{cap['profile']} / {cap['mcu']} / build {cap['build_id']}: {len(selection['files'])} files, {selection['total_bytes']} bytes")
    for name in selection['packages']:
        print('  + ' + name)
    for item in selection['skipped']:
        print('  - ' + item['package'] + ': ' + item['reason'])


class MkcSession:
    """One CDC session; the existing MKC clients own all serial/M8 framing."""
    def __init__(self, cap, *, port=None, mock=None, command=None):
        if command is None:
            command = (['powershell', '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT/'tools/.mkc/mkc.ps1')]
                       if os.name == 'nt' else ['bash', str(ROOT/'tools/.mkc/mkc.sh')])
        args = [*command, '--bundle-session', '--expect-profile', cap['device_profile'], '--expect-build', cap['build_id'], '--wait-ready', '45']
        if port:
            args += ['--port', port]
        if mock:
            args += ['--mock', str(mock)]
        self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1)
        if self._response() != '@BUNDLE READY':
            self.close()
            raise ValueError('MKC could not start a matching firmware session')
    def _response(self):
        for line in self.process.stdout:
            line = line.rstrip('\r\n')
            if line.startswith('@BUNDLE '):
                return line
            print(line, file=__import__('sys').stderr)
        return ''
    def call(self, operation, remote, local=''):
        if any(c in str(remote) + str(local) for c in '\t\r\n\0'):
            raise ValueError('invalid session path')
        self.process.stdin.write('\t'.join((operation, remote, str(local))) + '\n')
        self.process.stdin.flush()
        reply = self._response()
        if reply != '@BUNDLE OK':
            raise OSError(reply or 'MKC session ended')
    def close(self):
        if getattr(self, 'process', None) is not None:
            if self.process.poll() is None:
                self.process.stdin.close()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    self.process.wait(timeout=10)
            self.process.stdout.close()
            if self.process.returncode:
                raise OSError('MKC session failed')


def synchronize(selection, session, *, verify=False):
    cap = selection['capabilities']
    with tempfile.TemporaryDirectory(prefix='mk61-program-sync-') as directory:
        temp = Path(directory)
        cache = {}
        def entries(parent):
            key = parent.casefold()
            if key not in cache:
                path = temp / 'listing'
                session.call('LIST', actual_name(parent) if parent != '/' else '/', path)
                found = {}
                for line in path.read_text(encoding='utf-8').splitlines():
                    kind, size, name = line.split('\t', 2)
                    found[name.casefold()] = (kind, name)
                cache[key] = found
            return cache[key]
        def exists(name):
            path = PurePosixPath(name)
            parent = str(path.parent)
            if parent != '/' and not exists(parent):
                return False
            return path.name.casefold() in entries(parent)
        def actual_name(name):
            path = PurePosixPath(name)
            if name == '/':
                return '/'
            parent = actual_name(str(path.parent))
            item = entries(parent).get(path.name.casefold())
            return parent.rstrip('/') + '/' + (item[1] if item else path.name)
        def get(name):
            path = temp / 'download'
            session.call('GET', actual_name(name), path)
            return logical(path.read_bytes(), name)
        def mkdir(parent):
            if parent == '/':
                return
            ancestor = str(PurePosixPath(parent).parent)
            mkdir(ancestor)
            if not exists(parent):
                session.call('MKDIR', actual_name(parent))
                cache.pop(ancestor.casefold(), None)
            elif entries(ancestor)[PurePosixPath(parent).name.casefold()][0] != 'd':
                raise ValueError('destination parent is not a directory: ' + parent)
        for module in selection.get('system_files', []):
            remote = '/System/' + module['path']
            if not exists(remote):
                raise ValueError('missing ' + remote + '; install the matching System bundle first')
            entry = entries(str(PurePosixPath(remote).parent))[PurePosixPath(remote).name.casefold()]
            if entry[0] != 'f':
                raise ValueError('invalid System dependency: ' + remote)
            if verify and sha(get(remote)) != module['sha256']:
                raise ValueError('outdated ' + remote + '; install the matching System bundle first')
        receipt = {}
        old_index = []
        if exists(RECEIPT):
            index = json.loads(get(RECEIPT).decode('utf-8'))
            if (index.get('format') != 1 or not re.fullmatch('[0-9a-f]{64}', index.get('sha256', ''))
                    or type(index.get('parts')) is not int or not 1 <= index['parts'] <= 256):
                raise ValueError('invalid previous program receipt index')
            old_index = [f"/System/ProgramIndex/{index['sha256'][:12]}-{i:03}.TXT" for i in range(index['parts'])]
            packed = b''.join(get(name) for name in old_index)
            decoder = zlib.decompressobj()
            try:
                raw = decoder.decompress(base64.b64decode(packed, validate=True), 1024*1024+1)
            except zlib.error as error:
                raise ValueError('corrupt previous program receipt') from error
            if not decoder.eof or decoder.unused_data or len(raw) > 1024*1024 or sha(raw) != index['sha256']:
                raise ValueError('corrupt previous program receipt')
            previous = json.loads(raw.decode('utf-8'))
            if previous.get('format') != 1 or not isinstance(previous.get('files'), dict):
                raise ValueError('invalid previous program receipt')
            for name, digest in previous['files'].items():
                safe_path(name)
                if name.split('/')[0] not in ('games', 'app', 'apps', 'library', 'examples', 'sheets', 'CHIP8', 'Fonts') or not re.fullmatch('[0-9a-f]{64}', digest):
                    raise ValueError('invalid owned path in previous receipt')
            receipt = previous['files']
        incoming = {f['path']: f for f in selection['files']}
        incoming_names = {name.casefold() for name in incoming}
        receipt_folded = {name.casefold(): digest for name, digest in receipt.items()}
        owned, retained = {}, []
        # Prepare a complete update before touching the device. Existing files
        # are read to distinguish installed originals from user modifications;
        # this is independent of optional post-upload verification.
        operations = []
        for name, record in incoming.items():
            source = Path(record['source'])
            data = logical(source.read_bytes(), name)
            if sha(data) != record['sha256']:
                raise ValueError('source changed after preflight: ' + str(source))
            remote = '/' + name
            if exists(remote):
                # No write is needed when the packaged default did not change.
                # Keep its original baseline hash so a later update/removal
                # can still distinguish a user's edits without reading now.
                if not verify and receipt_folded.get(name.casefold()) == record['sha256']:
                    owned[name] = record['sha256']
                    continue
                current = sha(get(remote))
                if current == record['sha256']:
                    owned[name] = current
                    continue
                if receipt_folded.get(name.casefold()) != current:
                    retained.append(name)
                    continue
            staged = temp / ('upload-' + str(len(operations)))
            staged.write_bytes(data)
            operations.append(('PUT', remote, staged, record['sha256']))
            owned[name] = record['sha256']
        for name, digest in receipt.items():
            if name.casefold() not in incoming_names and exists('/' + name):
                if sha(get('/' + name)) == digest:
                    operations.append(('REMOVE', actual_name('/' + name), None, digest))
                else:
                    retained.append(name)
        for operation, remote, source, expected in operations:
            if operation == 'PUT':
                mkdir(str(PurePosixPath(remote).parent))
                session.call('PUT', actual_name(remote), source)
                if verify and sha(get(remote)) != expected:
                    raise ValueError('readback mismatch: ' + remote)
            else:
                session.call('REMOVE', remote)
            cache.pop(str(PurePosixPath(remote).parent).casefold(), None)
            print(operation.lower() + ' ' + remote)
        mkdir('/System')
        result = dict(format=1, build_id=cap['build_id'], files=owned)
        raw = (json.dumps(result, ensure_ascii=True, sort_keys=True) + '\n').encode('utf-8')
        packed = base64.b64encode(zlib.compress(raw))
        pieces = [packed[i:i+1200] for i in range(0, len(packed), 1200)]
        if len(pieces) > 256:
            raise ValueError('program receipt exceeds supported size')
        mkdir('/System/ProgramIndex')
        new_index = []
        for i, piece in enumerate(pieces):
            remote = f"/System/ProgramIndex/{sha(raw)[:12]}-{i:03}.TXT"
            part = temp / 'part.txt'
            part.write_bytes(piece)
            session.call('PUT', remote, part)
            if verify and get(remote) != piece:
                raise ValueError('receipt part readback mismatch')
            new_index.append(remote)
        receipt_file = temp / 'PROGRAMS.TXT'
        receipt_file.write_text(json.dumps(dict(format=1, sha256=sha(raw), parts=len(pieces))) + '\n', encoding='utf-8')
        session.call('PUT', RECEIPT, receipt_file)
        if verify and get(RECEIPT) != receipt_file.read_bytes():
            raise ValueError('receipt readback mismatch')
        for name in old_index:
            if name not in new_index:
                session.call('REMOVE', name)
        for name in retained:
            print('preserved user file /' + name)
        return dict(installed=sum(op[0] == 'PUT' for op in operations), removed=sum(op[0] == 'REMOVE' for op in operations), preserved=retained)


def export(selection, output):
    # Export to a new directory only; never synchronize user data on an SD card
    # through this packaging path.
    if output.exists():
        raise ValueError('export directory must not exist: ' + str(output))
    snapshots = []
    for record in selection['files']:
        source = Path(record['source'])
        raw = source.read_bytes()
        if sha(logical(raw, record['path'])) != record['sha256']:
            raise ValueError('source changed after planning')
        snapshots.append(raw)
    output.mkdir(parents=True)
    for record, raw in zip(selection['files'], snapshots):
        target = output / record['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (output / 'programs-manifest.json').write_text(json.dumps(distribution_manifest(selection), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def distribution_manifest(selection):
    return {**selection, 'files': [{k: v for k, v in record.items() if k != 'source'} for record in selection['files']]}
