"""Correlate one command without losing the source-defined async notices."""
import re
from session import Hold


def correlated(command,reply):
    if not reply.endswith('\r\nmk61> '):raise Hold('Incomplete Pico command suffix')
    echoes=list(re.finditer(r'(?m)^'+re.escape(command)+r'\r\n',reply))
    if len(echoes)!=1:raise Hold('Missing/duplicate exact Pico command echo')
    offset=echoes[0].start();prefix=reply[:offset]
    if len(prefix)>1024 or prefix and not prefix.endswith('\r\n'):
        raise Hold('Incomplete/unbounded async prefix')
    for line in prefix.split('\r\n')[:-1] if prefix else ():
        if line=='PICOCALC PANEL INITIALIZED KBD=OK':continue
        if re.fullmatch(r'X=\[[^\x00-\x1f\x7f\[\]]{0,32}\]',line):continue
        raise Hold('Unknown/error async Pico prefix')
    result=reply[offset:]
    if result.count('\r\nmk61> ')!=1:raise Hold('Ambiguous Pico command prompt')
    return result,prefix
