#!/usr/bin/env python3
"""Pure admission for a fresh, complete response from one exact uploaded APP."""
import re


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def validate(exchange, target, app_bytes, first_status, correlate, canonical, allowed, framed=False):
    require(app_bytes[:8] == b'MK61APP\0' and len(app_bytes) >= 64, 'Invalid exact APP header')
    memory = int.from_bytes(app_bytes[32:36], 'little')
    image_crc = int.from_bytes(app_bytes[52:56], 'little')
    command = 'open "' + target + '"'
    correlated, prefix = correlate(command, exchange.decode('cp1251', 'strict'), first_status)
    body = canonical(command, correlated)
    match = re.fullmatch(
        r'(?P<frame>(?:IFO4:[ -~]*\r\n)*)'
        r'APP_RESULT=0 CRC=(?P<crc>[0-9A-F]{8}) MEMORY=(?P<memory>[0-9]+)\r\n'
        r'APP_FLOW_RESULT=(?P<result>[0-9]+)(?P<error>\r\nERROR)?', body)
    require(match is not None, 'Incomplete, duplicated, or unexpected APP envelope')
    require(match['crc'] == f'{image_crc:08X}' and match['memory'] == str(memory),
            'APP image CRC or resident memory does not match the uploaded APP')
    code = int(match['result'])
    require(code in allowed and bool(match['error']) == bool(code), 'Unexpected APP result or error tail')
    require(bool(match['frame']) == bool(framed), 'Unexpected or missing result frame')
    return code
