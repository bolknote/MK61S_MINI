"""Independent checksum for the finite integer clock workload."""
def oracle(count):
    value = 0x31415926
    for _ in range(count):
        value ^= (value << 13) & 0xFFFFFFFF
        value ^= value >> 17
        value ^= (value << 5) & 0xFFFFFFFF
    return value
