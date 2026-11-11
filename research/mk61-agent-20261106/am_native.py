"""The same native model can emit a forced WRITE hypothesis, then raw actions."""
from aj_native import Engine as Parent, prepare_source, MAX_INPUT_BYTES
from am_common import ACTION_IDS


class Engine(Parent):
    def prefill(self, text, segmented=False):
        state = super().prefill(text, segmented)
        if state is not None and segmented and getattr(self, 'force_write', False):
            state[1].value = ACTION_IDS[0]
        return state

    def plan(self, text):
        self.force_write = True
        try: return self.generate(text)
        finally: self.force_write = False
