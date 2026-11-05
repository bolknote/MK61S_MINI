"""Check host prerequisites before constructing the native Unicorn engine.

On macOS/arm64, Unicorn 2.1.4 falls back to MRS CTR_EL0 when the sandbox
rejects hw.cachelinesize. That fallback can raise SIGILL before guest code
runs. Reject that environment before calling native code, without patching
Unicorn or trying to escape the sandbox.
"""
import ctypes
import os
import platform


class UnicornHostError(RuntimeError):
    """The host environment cannot initialize Unicorn safely."""


def ensure_compatible_host():
    if platform.system() != 'Darwin' or platform.machine().lower() not in ('arm64', 'aarch64'):
        return
    libc = ctypes.CDLL(None, use_errno=True)
    query = libc.sysctlbyname
    query.argtypes = [ctypes.c_char_p, ctypes.c_void_p,
                      ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p, ctypes.c_size_t]
    query.restype = ctypes.c_int
    value = ctypes.c_long(0)
    size = ctypes.c_size_t(ctypes.sizeof(value))
    ctypes.set_errno(0)
    result = query(b'hw.cachelinesize', ctypes.byref(value), ctypes.byref(size), None, 0)
    error = ctypes.get_errno()
    if result != 0 or value.value <= 0:
        reason = f'errno={error}: {os.strerror(error)}' if result else 'invalid cache line size'
        raise UnicornHostError(
            'Unicorn cannot start safely on this macOS host: hw.cachelinesize '
            f'failed ({reason}). Its CTR_EL0 fallback may cause SIGILL. '
            'Run the same ARM test outside the sandbox through normal tool approval. '
            'No emulator was constructed.')


def Uc(*args, **kwargs):
    """Construct the unchanged native engine only after the host check passes."""
    ensure_compatible_host()
    from unicorn import Uc as NativeUc
    return NativeUc(*args, **kwargs)
