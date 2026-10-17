"""RP2040 UF2 packaging (Microsoft UF2 512-byte block format).

The SDK produces the linked BIN including boot2 and its checksum. This module
only wraps that image for the RP2040 ROM; it does not create boot code.
Specification: https://github.com/microsoft/uf2/blob/master/README.md
"""
import struct

FLASH_BASE = 0x10000000
FLASH_SIZE = 2 * 1024 * 1024
FAMILY_ID = 0xE48BFF56
MAGIC0, MAGIC1, MAGIC_END = 0x0A324655, 0x9E5D5157, 0x0AB16F30


def encode(image):
    if not image or len(image) > FLASH_SIZE:
        raise ValueError("Pico H image must fit its 2-MiB flash")
    blocks = (len(image) + 255) // 256
    result = bytearray()
    for index in range(blocks):
        result += struct.pack("<8I", MAGIC0, MAGIC1, 0x2000,
                              FLASH_BASE + index * 256, 256, index, blocks, FAMILY_ID)
        result += image[index * 256:(index + 1) * 256].ljust(256, b"\0")
        result += bytes(220)
        result += struct.pack("<I", MAGIC_END)
    return bytes(result)


def validate(data, image):
    """Check transport headers and reconstruct the exact linked BIN."""
    if not data or len(data) % 512:
        raise ValueError("Incomplete UF2 blocks")
    blocks = len(data) // 512
    reconstructed = bytearray()
    for index in range(blocks):
        block = data[index * 512:(index + 1) * 512]
        expected = (MAGIC0, MAGIC1, 0x2000, FLASH_BASE + index * 256,
                    256, index, blocks, FAMILY_ID)
        if struct.unpack_from("<8I", block) != expected or \
                struct.unpack_from("<I", block, 508)[0] != MAGIC_END:
            raise ValueError("Invalid RP2040 UF2 header")
        reconstructed += block[32:288]
    if not image or len(image) > FLASH_SIZE or \
            blocks != (len(image) + 255) // 256 or \
            reconstructed != image.ljust(blocks * 256, b"\0"):
        raise ValueError("UF2 payload differs from the linked BIN")
