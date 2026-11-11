"""Run the standalone four-class critic in the existing portable Q4 engine."""
import ctypes as C
from pathlib import Path
from ao_common import CLASSES, DIAG_IDS
from aj_native import prepare_source, MAX_INPUT_BYTES


class Engine:
    def __init__(self, root, arm='adapt'):
        self.root = Path(root)
        self.lib = C.CDLL(str(self.root / 'native/codec-probe.dylib'))
        self.lib.mk_ai_open.argtypes = [C.c_void_p, C.c_uint]
        self.lib.codec_set_mask.argtypes = [C.POINTER(C.c_ushort), C.c_uint]
        self.lib.codec_forward.argtypes = [C.c_ushort, C.c_int, C.POINTER(C.c_ushort), C.POINTER(C.c_float)]
        self.lib.codec_encode.argtypes = [C.c_char_p, C.POINTER(C.c_ushort), C.c_uint, C.POINTER(C.c_uint)]
        self.capacity = max((self.root / 'export' / a / 'model.mka').stat().st_size for a in ['head', 'adapt'])
        self.buffer = C.create_string_buffer(self.capacity)
        self.arm = None
        self.open(arm)

    def open(self, arm):
        if self.arm == arm:
            return
        path = self.root / 'export' / arm / 'model.mka'
        size = path.stat().st_size
        with path.open('rb') as stream:
            assert stream.readinto(memoryview(self.buffer).cast('B')[:size]) == size
        assert self.lib.mk_ai_open(self.buffer, size) == 0
        allowed = (C.c_ushort * len(DIAG_IDS))(*DIAG_IDS)
        self.lib.codec_set_mask(allowed, len(allowed))
        self.arm = arm

    def classify(self, text):
        assert text.endswith('<') and len(text.encode()) <= MAX_INPUT_BYTES
        encoded = (C.c_ushort * 1024)()
        used = C.c_uint()
        assert self.lib.codec_encode(text[:-1].encode(), encoded, 1023, C.byref(used)) == 0
        encoded[used.value] = 30
        used.value += 1
        assert used.value < 1024
        inputs = list(encoded[:used.value])
        best = C.c_ushort()
        logits = (C.c_float * 8224)()
        self.lib.mk_ai_reset()
        for i, token in enumerate(inputs):
            last = i + 1 == len(inputs)
            assert self.lib.codec_forward(token, int(last), C.byref(best), logits if last else None) == 0
        values = [float(logits[i]) for i in DIAG_IDS]
        prediction = max(range(4), key=values.__getitem__)
        assert best.value == DIAG_IDS[prediction]
        return {'predicted': prediction, 'class': CLASSES[prediction], 'logits': values, 'input_token_ids': inputs}
