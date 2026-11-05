#!/usr/bin/env python3
"""Prepare file-backed Spectrum media: FAT16 SD image or blank TR-DOS disk."""
import argparse
from pathlib import Path
import struct
import zipfile


def blank_trd():
    disk = bytearray(655360)
    disk[0x8E1:0x8E8] = bytes([0, 1, 0x16, 0, 0xF0, 9, 0x10])
    disk[0x8F5:0x8FD] = b"PICOCALC"
    return disk


def fat_image(files, size_mib=16):
    """16 or 32 MiB FAT16, one MBR partition, 8.3 names, deterministic contents."""
    if size_mib not in (16, 32):
        raise ValueError("FAT image size must be 16 or 32 MiB")
    sectors, start, reserved, fats, fat_sectors, root_entries, cluster_sectors = size_mib * 2048, 63, 1, 2, size_mib * 4, 512, 2
    image = bytearray(sectors * 512)
    volume = memoryview(image)[start * 512:]
    part_sectors = sectors - start
    image[446:462] = struct.pack("<B3sB3sII", 0, b"\1\1\0", 6, b"\xFE\xFF\xFF", start, part_sectors)
    image[510:512] = b"\x55\xAA"
    volume[:3] = b"\xEB\x3C\x90"
    volume[3:11] = b"MK61S   "
    struct.pack_into("<HBHBHHBHHHII", volume, 11, 512, cluster_sectors, reserved, fats, root_entries,
                     part_sectors, 0xF8, fat_sectors, 32, 64, start, 0)
    volume[36:39] = b"\x80\0\x29"
    struct.pack_into("<I", volume, 39, 0x4D4B3631)
    volume[43:54] = b"PICOCALC   "
    volume[54:62] = b"FAT16   "
    volume[510:512] = b"\x55\xAA"
    root_at = (reserved + fats * fat_sectors) * 512
    data_at = root_at + root_entries * 32
    cluster_bytes = cluster_sectors * 512
    fat = bytearray(fat_sectors * 512)
    struct.pack_into("<HH", fat, 0, 0xFFF8, 0xFFFF)
    next_cluster = 2

    def allocate(data):
        nonlocal next_cluster
        count = max(1, (len(data) + cluster_bytes - 1) // cluster_bytes)
        first = next_cluster
        if data_at + (first + count - 2) * cluster_bytes > len(volume):
            raise ValueError("files do not fit in the SD image")
        for i in range(count):
            c = next_cluster
            next_cluster += 1
            struct.pack_into("<H", fat, c * 2, 0xFFFF if i == count - 1 else c + 1)
            block = data[i * cluster_bytes:(i + 1) * cluster_bytes]
            at = data_at + (c - 2) * cluster_bytes
            volume[at:at + len(block)] = block
        return first

    tree = {}
    for path, data in files.items():
        node = tree
        parts = path.upper().strip("/").split("/")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = data

    def entry(name, directory, cluster, size):
        base, _, ext = name.partition(".")
        if len(base) > 8 or len(ext) > 3 or not base:
            raise ValueError("FAT image requires 8.3 names: " + name)
        out = bytearray(32)
        out[:11] = (base.ljust(8) + ext.ljust(3)).encode("ascii")
        out[11] = 16 if directory else 32
        struct.pack_into("<H", out, 26, cluster)
        struct.pack_into("<I", out, 28, size)
        return out

    def directory(node, parent=0, root=False):
        size = max(cluster_bytes, ((len(node) + 3) * 32 + cluster_bytes - 1) // cluster_bytes * cluster_bytes)
        cluster = 0 if root else allocate(bytes(size))
        entries = bytearray()
        if not root:
            entries += bytes(32)
            entries[:11] = b".          "
            entries[11] = 16
            struct.pack_into("<H", entries, 26, cluster)
            dotdot = bytearray(32)
            dotdot[:11] = b"..         "
            dotdot[11] = 16
            struct.pack_into("<H", dotdot, 26, parent)
            entries += dotdot
        for name, data in sorted(node.items()):
            is_dir = isinstance(data, dict)
            child = directory(data, cluster) if is_dir else allocate(data)
            entries += entry(name, is_dir, child, 0 if is_dir else len(data))
        at = root_at if root else data_at + (cluster - 2) * cluster_bytes
        volume[at:at + len(entries)] = entries
        return cluster

    directory(tree, root=True)
    for i in range(fats):
        at = (reserved + i * fat_sectors) * 512
        volume[at:at + len(fat)] = fat
    return image


def esxdos_image(package):
    with zipfile.ZipFile(package) as archive:
        files = {p: archive.read(p) for p in archive.namelist()
                 if not p.endswith("/") and p.startswith(("SYS/", "BIN/"))}
    files["HELLO.TXT"] = b"PicoCalc DivMMC image\r\n"
    return fat_image(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--esxdos", type=Path, help="esxDOS release ZIP; creates FAT16 SD image")
    args = parser.parse_args()
    args.output.write_bytes(esxdos_image(args.esxdos) if args.esxdos else blank_trd())


if __name__ == "__main__":
    main()
