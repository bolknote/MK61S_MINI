"""Conservative CDC writes with CRC, exact offsets and full file readback."""
import hil_c6_system_bootstrap as protocol
from hil_c5_stack import read_file

# The shared Classic occasionally loses the end of an echo/ACK with longer
# commands. Keep strict acknowledgement checks and shorten the data packets.
protocol.CHUNK_SIZE = 32


def write_file(port, path, data):
    protocol.write_file(port, path, data)
    assert read_file(port, path) == data, path
