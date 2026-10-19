#!/usr/bin/env python3
"""Offline builder, source aliases, quoted paths and failure atomicity."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zlib
from compare_linked_chess_images import compare

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='mk61-linked-cli-') as temporary:
    work=Path(temporary);basic=work/'basic with spaces.tbi';focal=work/'Фокал.foc'
    basic.write_text('10 A=1;END\n');focal.write_text('1.10 S A=2;E\n')
    manifest=work/'members.json';output=work/'program.lvp'
    data={'entry':1,'members':[
        {'symbol':1,'language':'basic','path':basic.name},
        {'symbol':2,'language':'focal','path':focal.name},
        {'symbol':3,'language':'basic','path':basic.name}]}
    manifest.write_text(json.dumps(data))
    command=[sys.executable,str(ROOT/'tools/build_vm_program.py'),str(manifest),'-o',str(output),'--compiler','clang++']
    subprocess.run(command,check=True)
    image=output.read_bytes()
    assert image[:4]==b'LVP1' and struct.unpack_from('<H',image,6)[0]==3
    assert struct.unpack_from('<I',image,8)[0]==len(image)
    assert struct.unpack_from('<I',image,24)[0]==zlib.crc32(image[32:])
    assert struct.unpack_from('<I',image,28)[0]==zlib.crc32(image[:28])
    first,second,alias=[struct.unpack_from('<4I',image,32+16*i) for i in range(3)]
    assert first[0]==1 and alias[0]==3 and first[1:]==alias[1:]
    assert second[1]+second[2]==len(image) and first[3]!=second[3]
    cache=work/'cache';bank=cache/'0010'/'Image0';bank.mkdir(parents=True)
    member=image[first[1]:first[1]+first[2]]
    page=bank/'00000000.bin';page.write_bytes(member+bytes(1024-len(member)))
    metadata=bytearray(64);metadata[:4]=b'LFP1';metadata[5]=14;metadata[16:48]=member[:32]
    struct.pack_into('<I',metadata,60,zlib.crc32(metadata[:60]))
    (cache/'0010'/'Manifest.bin').write_bytes(metadata)
    assert compare(output,cache)==(1,1,2)
    damaged_page=bytearray(page.read_bytes());damaged_page[len(member)-1]^=1;page.write_bytes(damaged_page)
    try:compare(output,cache)
    except AssertionError:pass
    else:raise AssertionError('cached bytecode mismatch accepted')
    for damaged in (
        {'entry':True,'members':data['members']},
        {'entry':7,'members':data['members']},
        {'entry':1,'members':[data['members'][0],data['members'][0]]},
        {'entry':1,'members':[{'symbol':1,'language':'bad','path':basic.name}]}):
        manifest.write_text(json.dumps(damaged))
        result=subprocess.run(command,capture_output=True)
        assert result.returncode and output.read_bytes()==image
    manifest.write_text(json.dumps(data));manifest_before=manifest.read_bytes()
    alias_path=work/'source-alias.lvp';alias_path.symlink_to(basic)
    hardlink_path=work/'source-hardlink.lvp';hardlink_path.hardlink_to(basic)
    for protected in (basic,manifest,alias_path,hardlink_path):
        collision=command.copy();collision[collision.index('-o')+1]=str(protected)
        assert subprocess.run(collision,capture_output=True).returncode
        assert manifest.read_bytes()==manifest_before and output.read_bytes()==image
    assert basic.read_text()=='10 A=1;END\n' and focal.read_text()=='1.10 S A=2;E\n'
print('linked VM builder: manifest, BASIC/FOCAL, shared aliases, quoted paths and rejected inputs PASS')
