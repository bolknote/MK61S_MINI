#!/usr/bin/env python3
"""Download pinned game media locally; no game binaries belong in Git."""
import sys as _repo_sys
from pathlib import Path as _RepoPath
_repo_sys.path.insert(0, str(_RepoPath(__file__).resolve().parents[3]))
import argparse
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile

from tools.apps.spectrum.build_spectrum_library import LIBRARY, READY_LIBRARY, prepare
from tools.apps.spectrum.fetch_spectrum_devices import SOURCES


def checked(data, expected, label):
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Checksum mismatch: ' + label)
    return data


def fetch(url, expected, label):
    with urlopen(Request(url, headers={'User-Agent': 'MK61S-Spectrum-library/1'}), timeout=60) as response:
        return checked(response.read(), expected, label)


def package_zip(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return output.getvalue()


def download_package(package, entries, cache):
    path = LIBRARY / package['archive']
    if path.exists():
        checked(path.read_bytes(), package['sha256'], str(path))
        print('Verified local ' + package['title'], flush=True)
        return
    if package['id'] == 'ianna':
        data = fetch(package['download_url'], package['sha256'], package['title'])
    elif package['id'] == 'cosmic-payback':
        upstream = cache / 'Cosmic-Payback.tap'
        if upstream.exists():
            tap = checked(upstream.read_bytes(), package['download_sha256'], str(upstream))
        else:
            tap = fetch(package['download_url'], package['download_sha256'], 'Cosmic Payback TAP')
            upstream.write_bytes(tap)
        notice = (LIBRARY / 'cosmic-payback/LICENSE.TXT').read_bytes()
        data = package_zip({'COSMIC.TAP': tap, 'LICENSE.TXT': notice})
    else:
        upstream = cache / package['upstream_archive']
        if upstream.exists():
            original = checked(upstream.read_bytes(), package['upstream_sha256'], str(upstream))
        else:
            # itch.io's public free-download endpoint supplies a temporary CDN URL.
            request = Request(package['source'] + '/file/' + str(package['upstream_upload_id']),
                              data=urlencode({'action': 'download'}).encode(),
                              headers={'Referer': package['source'], 'User-Agent': 'MK61S-Spectrum-library/1'})
            with urlopen(request, timeout=60) as response:
                link = json.load(response)['url']
            original = fetch(link, package['upstream_sha256'], package['upstream_archive'])
            upstream.write_bytes(original)
        with zipfile.ZipFile(io.BytesIO(original)) as archive:
            files = {}
            for entry in entries:
                name = entry['member']
                source = 'games/Vortex/legal.txt' if name in ('VORTEX.TXT', 'games/Vortex/VORTEX.TXT') else name
                files[name] = checked(archive.read(source), entry['sha256'], name)
        data = package_zip(files)
    checked(data, package['sha256'], package['title'])
    # Verify every original member as well as the complete pinned package.
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for entry in entries:
            checked(archive.read(entry['member']), entry['sha256'], entry['member'])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.zip.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)
    print('Downloaded ' + package['title'], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=LIBRARY.parents[1] / '.build/spectrum-downloads')
    parser.add_argument('--archives-only', action='store_true', help='download packages without building GAMES.img')
    parser.add_argument('--package', action='append', dest='packages', metavar='ID',
                        help='download only this catalog package; may be repeated')
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    catalog = json.loads((LIBRARY / 'catalog.json').read_text())
    available = {package['id']: package for package in catalog['packages']}
    selected = args.packages or list(available)
    unknown = [package_id for package_id in selected if package_id not in available]
    if unknown:
        parser.error('unknown package: ' + ', '.join(unknown))
    for package_id in dict.fromkeys(selected):
        package = available[package_id]
        entries = [e for e in catalog['entries'] if e['package'] == package['id']]
        download_package(package, entries, args.cache)
    if not args.archives_only:
        if set(selected) != set(available):
            parser.error('building GAMES.img requires every package; use --archives-only for a subset')
        source = SOURCES['esxdos089.zip']
        esxdos = args.cache / 'esxdos089.zip'
        if not esxdos.exists():
            esxdos.write_bytes(fetch(source['url'], source['sha256'], 'esxDOS 0.8.9'))
        checked(esxdos.read_bytes(), catalog['esxdos']['sha256'], str(esxdos))
        prepare(READY_LIBRARY, esxdos, report_dir=LIBRARY.parents[1] / '.build/spectrum-library')
        print('Built ' + str(READY_LIBRARY / 'GAMES.img'), flush=True)


if __name__ == '__main__':
    main()
