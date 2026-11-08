import struct
def stress_rom():
    # Fill64x32 once, then XOR one8x8 tile forever: dirty at every60Hz tick,
    # mostly full bitmap, no input or program-specific execution shortcut.
    words=[0x00E0,0xA220,0x6100,0x6000,0xD011,0x7008,0x3040,0x1208,
           0x7101,0x3120,0x1206,0x6000,0x6100,0xD018,0x121A,0]
    return b''.join(struct.pack('>H',word) for word in words)+b'\xFF'*8
