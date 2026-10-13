"""Pinned ROM descriptors and transfer deadline, without opening hardware."""
import ast
from pathlib import Path
from hil_system_memory import SERIAL, valid_classic_dfu_listing

def listing(serial=SERIAL):
    names=('@Internal Flash /0x08000000/04*016Kg,01*064Kg,03*128Kg',
           '@Option Bytes /0x1FFFC000/01*016 e',
           '@OTP Memory /0x1FFF7800/01*512 e',
           '@Device Feature /0xFFFF0000/01*004 e')
    return '\n'.join(f'Found DFU: [0483:df11] ver=2200, devnum=4, cfg=1, intf=0, path="1-2", alt={alt}, name="{name}", serial="{serial}"'
                     for alt,name in enumerate(names))

good=listing()
assert valid_classic_dfu_listing(good,'')
assert valid_classic_dfu_listing(good.replace('@Internal Flash /','@Internal Flash  /'),'')
assert not valid_classic_dfu_listing(listing('another-device'),'')
assert not valid_classic_dfu_listing(good+'\n'+listing('another-device'),'')
assert not valid_classic_dfu_listing(good,'Broken LANGID string descriptor')
assert not valid_classic_dfu_listing(good+'\nBroken LANGID','')
assert not valid_classic_dfu_listing(good.replace('@Internal Flash','UNKNOWN'),'')
assert not valid_classic_dfu_listing(good.replace('@Internal Flash','@OTP'),'')
assert not valid_classic_dfu_listing(good.replace('0x08000000','0x20000000'),'')
assert not valid_classic_dfu_listing('\n'.join(good.splitlines()[:3]),'')
assert not valid_classic_dfu_listing(good,'',1)
tree=ast.parse(Path(__file__).with_name('hil_system_memory.py').read_text())
flash=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='flash')
downloads=[node for node in ast.walk(flash) if isinstance(node,ast.Call) and
           isinstance(node.func,ast.Attribute) and node.func.attr=='run' and node.args and
           isinstance(node.args[0],ast.Name) and node.args[0].id=='command']
assert len(downloads)==1
timeout=next(kw.value for kw in downloads[0].keywords if kw.arg=='timeout')
assert isinstance(timeout,ast.Constant) and timeout.value>=180
print('DFU safety: exact UID/all ROM alts/Internal Flash, unknown descriptors rejected, timeout>=180 PASS')
