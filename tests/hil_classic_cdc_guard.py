"""OS-only Classic binding/holder checks, extracted from Bytecode preflight.

No serial device is opened. macOS libproc queries the exact cu/tty pair,
avoiding lsof scans of unrelated network volumes.
"""
if not __debug__:
    raise RuntimeError('Classic CDC checks require assertions; run Python without -O/-OO')

import ctypes
import os
from pathlib import Path
import plistlib
import stat
import subprocess


def os_binding(nodes, path):
    found = []

    def walk(rows, ancestors=()):
        for node in rows:
            chain = ancestors + (node,)
            if node.get('IOCalloutDevice') == path:
                found.append(chain)
            walk(node.get('IORegistryEntryChildren', []), chain)

    walk(nodes)
    assert len(found) == 1, ('ambiguous/missing OS CDC binding', len(found))
    chain = found[0]
    leaf = chain[-1]
    assert leaf['IOObjectClass'] == 'IOSerialBSDClient'
    devices = [node for node in chain if node.get('IOObjectClass') == 'IOUSBHostDevice']
    assert devices
    device = devices[-1]
    assert (device.get('USB Serial Number'), device.get('idVendor'), device.get('idProduct')) == (
        '2068336B4731', 0x0483, 0x5740)
    interface = [node for node in chain if node.get('IOObjectClass') == 'IOUSBHostInterface'][-1]
    assert interface['USB Serial Number'] == device['USB Serial Number']
    assert any(node.get('IOObjectClass') == 'AppleUSBACMData' for node in chain)
    assert leaf['IODialinDevice'] == path.replace('/dev/cu.', '/dev/tty.', 1)
    return dict(callout=path, dialin=leaf['IODialinDevice'], usb=device['USB Serial Number'],
                device_id=device['IORegistryEntryID'], serial_id=leaf['IORegistryEntryID'],
                classes=[node['IOObjectClass'] for node in chain],
                vid=device['idVendor'], pid=device['idProduct'])


def current_binding(path):
    raw = subprocess.check_output(['ioreg', '-a', '-r', '-c', 'IOUSBHostDevice', '-l'], timeout=8)
    return os_binding(plistlib.loads(raw), path)


def path_holders(query, path):
    encoded = os.fsencode(path)
    size = query(1, 0, encoded, 0, None, 0)
    assert 0 < size <= 1024 * 1024, ('proc_listpidspath size/error', size, ctypes.get_errno())
    buffer = (ctypes.c_int * (size // ctypes.sizeof(ctypes.c_int) + 32))()
    count = query(1, 0, encoded, 0, buffer, ctypes.sizeof(buffer))
    assert 0 <= count < ctypes.sizeof(buffer) and count % ctypes.sizeof(ctypes.c_int) == 0, (
        'proc_listpidspath error/truncation', count, ctypes.get_errno())
    return list(buffer)[:count // ctypes.sizeof(ctypes.c_int)]


def require_no_holders(binding):
    lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
    query = lib.proc_listpidspath
    query.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_char_p,
                      ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]
    query.restype = ctypes.c_int
    lib.proc_name.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    lib.proc_name.restype = ctypes.c_int
    owners = []
    for path in (binding['callout'], binding['dialin']):
        assert Path(path).parent == Path('/dev') and stat.S_ISCHR(os.stat(path).st_mode)
        for pid in path_holders(query, path):
            name = ctypes.create_string_buffer(1024)
            lib.proc_name(pid, name, len(name))
            owners.append(dict(path=path, pid=pid, name=os.fsdecode(name.value)))
    assert not owners, ('named CDC holders; do not interrupt them', owners)
