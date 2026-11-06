"""Licensed author editions supplementing the fixed UrqW catalog."""
import hashlib
import json
import re
from pathlib import Path
import shutil
import uuid

from tools.apps.urq.qst2urq import decode_source, make_package
from tools.apps.urq.library import ROOT, SOURCES

LOCK_PATH = Path(__file__).with_name('extra-games.json')


def locked_sources():
    lock = json.loads(LOCK_PATH.read_text())
    if lock['version'] != 1 or lock['license'] != 'MIT':
        raise ValueError('unsupported supplementary source license')
    result = []
    for game in lock['games']:
        folder = SOURCES / game['id']
        source = (folder / 'original.qst').read_bytes()
        license_text = (folder / 'LICENSE.txt').read_bytes()
        if hashlib.sha256(source).hexdigest() != game['source_sha256']:
            raise ValueError('unreviewed supplementary QST: ' + game['id'])
        if hashlib.sha256(license_text).hexdigest() != lock['license_sha256']:
            raise ValueError('unreviewed supplementary license: ' + game['id'])
        if not license_text.startswith(b'MIT License\n'):
            raise ValueError('missing MIT permission notice')
        result.append((game, source, license_text))
    return lock, result


def prepare(game, original, lock):
    text = decode_source(original, game['encoding']).replace('\r\n', '\n').replace('\r', '\n')
    # UrqW trims the literal BTN description before expanding tags. Do that
    # statically for plain/conditional button lines, preserving P/PLN spaces.
    lines = text.split('\n')
    for index, line in enumerate(lines):
        plain = re.match(r'^\s*btn\s+', line, re.I)
        conditional = re.match(r'^\s*if\s+[^&]+\s+then\s+btn\s+[^&]+$', line, re.I)
        if (plain or conditional) and '&' not in line and ' else ' not in line.lower():
            lines[index] = line.rstrip(' \t')
    text = '\n'.join(lines)
    manifest = {'manifest_version': 1, 'urq_mode': game['mode'], 'game_encoding': 'UTF-8',
                'urqw_title': game['title'], 'urqw_game_lang': 'ru', 'mk61_zx0_parser': 'optimal',
                'urqw_game_ifid': str(uuid.uuid5(uuid.NAMESPACE_URL,
                    lock['repository'] + '/blob/' + lock['revision'] + '/' + game['source_file'])).upper()}
    details = {'version': 1, 'repository': lock['repository'], 'revision': lock['revision'],
               'files': {game['source_file']: game['source_sha256'], lock['license_file']: lock['license_sha256']},
               'license': lock['license'], 'changes': [
                   'CP1251 is decoded to UTF-8 and line endings are normalized.',
                   'Static BTN caption whitespace is trimmed as in the UrqW parser; P/PLN spacing is retained.',
                   'The original DOS/AkURQ commands, story text and item rules are preserved.',
                   'Optimal independent 512-byte ZX0 pages keep the existing device format.'],
               'verification': 'tests/urq_library_self_test.py'}
    return text, manifest, details


def publish(host, output, source_output, smoke):
    lock, reviewed = locked_sources()
    records = []
    for game, original, license_text in reviewed:
        text, manifest, details = prepare(game, original, lock)
        files, package = make_package(text.encode(), game['mode'], 'UTF-8', manifest)
        startup = smoke(host, files)
        target = output / game['id']
        metadata = source_output / game['id']
        target.mkdir(parents=True, exist_ok=True)
        metadata.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            (target / name).write_bytes(data)
        shutil.copy2(ROOT / 'doc/explorer-icons/games.wbmp', target / 'autoexec.wbmp')
        (metadata / 'original.qst').write_bytes(original)
        (metadata / 'source.qst').write_text(text, encoding='UTF-8')
        (metadata / 'LICENSE.txt').write_bytes(license_text)
        for name, content in (('manifest.json', manifest), ('adaptation.json', details), ('package.json', package)):
            (metadata / name).write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n')
        (metadata / 'AUTHORS.txt').write_text(
            game['title'] + '\n' + game['author'] + '\n' + lock['repository'] + '\nRevision: ' +
            lock['revision'] + '\nSource: ' + game['source_file'] + '\nLicense: MIT\n' +
            'Text/M8 package for MK61S and PicoCalc; original story and rules retained.\n')
        records.append({'id': game['id'], 'title': game['title'], 'author': game['author'],
                        'lang': 'ru', 'license': lock['license'], 'mode': game['mode'],
                        'source': lock['repository'], 'revision': lock['revision'],
                        'description': game['description'], 'adaptation': details,
                        'package': package, 'startup': startup, 'published': True, 'reasons': []})
        print(game['id'] + ': published (pinned MIT author edition)', flush=True)
    return records
