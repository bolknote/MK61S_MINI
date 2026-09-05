#!/usr/bin/env python3
"""Decode stable VFAT diagnostic numbers without storing English prose in MCU Flash.

Usage: python3 tools/vfat_diagnostic.py 'VFAT v=1 code=1221 ...'
or pipe a terminal transcript to this command. Unknown codes are never renamed.
"""
import re
import sys

MESSAGES = {
    0: 'No error',
    1201: 'Bad name',
    1202: 'Name too long',
    1203: 'Bad dirent',
    1210: 'Bad dir cluster',
    1211: 'Bad file cluster',
    1212: 'Cluster reused',
    1213: 'Kind changed',
    1214: 'Bad file chain',
    1215: 'Bad dir chain',
    1216: 'Extent reused',
    1217: 'Tree too deep',
    1218: 'Missing file data',
    1219: 'Cluster limit',
    1220: 'Empty file',
    1221: 'File too large',
    1230: 'Storage busy',
    1231: 'Cache write failed',
    1232: 'FAT read failed',
    1233: 'Root read failed',
    1234: 'Dir read failed',
    1235: 'File read failed',
    1240: 'Prepare failed',
    1241: 'Apply failed',
    1242: 'Prune failed',
    1243: 'Stage discard failed',
    1244: 'Dir extents failed',
    1250: 'APP stage failed',
    1251: 'APP restore failed',
    1252: 'Invalid APP',
    1253: 'Validation failed',
}


def describe(code: int) -> str:
    return MESSAGES.get(code, "Unknown VFAT error")


def main() -> None:
    report = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read()
    found = False
    for line in report.splitlines():
        match = re.match(r"VFAT v=1 code=(\d+)(?: |$)", line)
        if match:
            print(line)
            print(describe(int(match[1])))
            found = True
    if not found:
        raise SystemExit("No VFAT v=1 record found")


if __name__ == "__main__":
    main()
