"""Exact bounded replay cache for independent ROM executions, not task answers."""
import collections
import copy
from full_isa_vm import FullVM


class CachedVM(FullVM):
    def __init__(self, capacity=8192):
        super().__init__(); self.cache = collections.OrderedDict()
        self.capacity = min(capacity, max(8, (256 * 1024 * 1024) // max(1, self.context_bytes)))
        self.hits = 0; self.misses = 0

    def execute(self, code, values=None, *, angle='RAD', context=None, max_commands=256, max_frames=4096):
        if context is not None:
            return super().execute(code, values, angle=angle, context=context, max_commands=max_commands, max_frames=max_frames)
        key = (tuple(code), tuple(sorted((k, type(v).__name__, repr(v)) for k, v in (values or {}).items())), angle, max_commands, max_frames)
        if key in self.cache:
            self.hits += 1; value = self.cache.pop(key); self.cache[key] = value
            self.restore(value[1])
            return copy.deepcopy(value[0]), value[1]
        self.misses += 1
        result, state = super().execute(code, values, angle=angle, max_commands=max_commands, max_frames=max_frames)
        self.cache[key] = (copy.deepcopy(result), state)
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)
        return result, state
