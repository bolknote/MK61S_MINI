"""Compose a Pico diagnostic image from fresh full Flash backups, offline.

No device API is imported. A future transaction must supply the newly accepted
baseline and fresh backup hash; historical A748 artifacts grant no access.
"""
from session import Hold,sha

BASE=0x10000000
FLASH_BYTES=2*1024*1024
SETTINGS_OFFSET=FLASH_BYTES-8192
PAYLOAD_BASE=0x101e0000


def compose(backup_a,backup_b,baseline,native,payload,layout,*,
            original_sha256,baseline_sha256,native_sha256):
    """Replace only the sealed native prefix and separately proven free payload.

    The whole final erase/program image includes the original settings and
    every intervening byte. The native ELF/footer/provider is verified by the
    separate pico-native-proof.py before this composition is admitted.
    """
    if len(backup_a)!=FLASH_BYTES or backup_a!=backup_b:
        raise Hold('Pico fresh full Flash backups differ or are not 2 MiB')
    if sha(backup_a)!=original_sha256:
        raise Hold('Pico fresh full Flash differs from the current handoff')
    if not baseline or sha(baseline)!=baseline_sha256 or backup_a[:len(baseline)]!=baseline:
        raise Hold('Pico current baseline prefix differs from accepted source')
    if not native or sha(native)!=native_sha256 or max(len(baseline),len(native))>SETTINGS_OFFSET:
        raise Hold('Pico sealed native prefix differs or overlaps settings')
    if layout.get('cpu')!='m0' or layout.get('base')!=PAYLOAD_BASE:
        raise Hold('Pico payload does not use the separately reviewed base')
    if not payload or len(payload)!=layout.get('bytes') or sha(payload)!=layout.get('sha256'):
        raise Hold('Pico payload size/hash differs')
    start=PAYLOAD_BASE-BASE;end=start+len(payload);erase_end=(end+4095)&~4095
    if max(len(baseline),len(native))>start or erase_end>SETTINGS_OFFSET:
        raise Hold('Pico payload overlaps native code or the settings erase span')
    if backup_a[start:erase_end]!=b'\xff'*(erase_end-start):
        raise Hold('Pico payload erase span is not wholly unused')
    candidate=bytearray(backup_a)
    candidate[:len(native)]=native;candidate[start:end]=payload
    if (candidate[:len(native)]!=native or candidate[start:end]!=payload or
        candidate[len(native):start]!=backup_a[len(native):start] or
        candidate[end:]!=backup_a[end:]):
        raise Hold('Pico diagnostic changed bytes outside native/payload union')
    return bytes(candidate)
