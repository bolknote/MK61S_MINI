#!/usr/bin/env python3
"""Real updater state machine, every Flash mutation interrupted, ASan/UBSan."""
from pathlib import Path
import hashlib,json,os,struct,subprocess,tempfile,zipfile,zlib
ROOT=Path(__file__).resolve().parents[1]
def release():
    """The reviewed ROM image, SD payload and archived sources stay a set."""
    folder=ROOT/'firmware/picocalc-m3-boot'
    manifest=json.loads((folder/'manifest.json').read_text())
    for name,info in manifest['files'].items():
        path=folder/'sd/Apps/BIOS/BIOSUPD.APP' if name=='BIOSUPD.APP' else folder/name
        data=path.read_bytes()
        assert len(data)==info['bytes'] and hashlib.sha256(data).hexdigest()==info['sha256'],name
    package=(folder/'BIOS.M3U').read_bytes();header=package[:32];bios=package[32:]
    words=struct.unpack('<8I',header)
    assert words[:5]==(0x3155334d,1,0x410,0x08002000,len(bios))
    assert len(bios)<=0xd400 and not len(bios)%4
    assert words[5]==zlib.crc32(bios) and words[7]==zlib.crc32(header[:28])
    assert bios==(folder/'bios.bin').read_bytes()
    assert package==(folder/'sd/Apps/BIOS/BIOS.M3U').read_bytes()
    bootstrap=(folder/'bootstrap.bin').read_bytes();boot=(folder/'boot.bin').read_bytes()
    assert len(bootstrap)==0xf424 and len(boot)<=8192
    assert bootstrap[:8192]==boot+b'\xff'*(8192-len(boot))
    assert bootstrap[8192:8192+len(bios)]==bios
    assert bootstrap[0xf400:]==header+struct.pack('<I',0xc001cafe)
    with zipfile.ZipFile(folder/'source.zip') as archive:
        expected=json.loads(archive.read('expected.json'))
        for name,digest in expected['sources'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest()==digest,name
        for name,digest in expected['images'].items():
            assert manifest['files'][name]['sha256']==digest,name
    print('M3 release PASS: ROM bootstrap, BIOS/M3U, SD APP and source archive hashes')
def main():
    release()
    with tempfile.TemporaryDirectory(prefix='m3b-test-') as folder:
        binary=Path(folder)/'test'
        boot=ROOT/'ports/picocalc/bios/boot'
        cmd=['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-I'+str(boot)]
        if os.environ.get('MK61_TEST_SANITIZERS','1')!='0':cmd+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        cmd+=list(map(str,[ROOT/'tests/picocalc_m3_boot_self_test.c',boot/'update.c',boot/'wire.c']))+['-o',str(binary)]
        subprocess.run(cmd,check=True);subprocess.run([str(binary)],check=True,env={**os.environ,'UBSAN_OPTIONS':'halt_on_error=1'})
        appcmd=cmd[:]
        appcmd[appcmd.index(str(ROOT/'tests/picocalc_m3_boot_self_test.c'))]=str(ROOT/'tests/picocalc_m3_updater_self_test.c')
        appcmd+=['-I'+str(ROOT/'sdk/portable/include'),'-I'+str(ROOT/'code'),'-I'+str(ROOT/'sdk/coproc')]
        subprocess.run(appcmd,check=True)
        subprocess.run([str(binary)],check=True,env={**os.environ,'UBSAN_OPTIONS':'halt_on_error=1'})
if __name__=='__main__':main()
