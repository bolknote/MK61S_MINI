"""Use the proven CRC/offset/readback transport from the memory experiments."""
import hil_c6_system_bootstrap as protocol
from hil_c5_stack import read_file
protocol.CHUNK_SIZE=32

def write_file(port,path,data):
    protocol.write_file(port,path,data)
    assert read_file(port,path)==data,path
