"""Host port for the actual core1 frame-scope methods; no device access."""
from pathlib import Path

def production_scope(root: Path, clock: str):
    header=(root/'ports/picocalc/io_worker.hpp').read_text()
    first=header.index('class FrameDeadlineScope {')
    declaration=header[first:header.index('\n};',first)+3]
    source=(root/'ports/picocalc/io_worker.cpp').read_text()
    first=source.index('FrameDeadlineScope::FrameDeadlineScope(')
    methods=source[first:source.index('DeadlineStatistics deadline_statistics()',first)]
    return ('namespace io_worker {\nWorkerDeadlineTrace deadline_trace;\n'
            'unsigned frame_trace_core=1;\nunsigned get_core_num(){return frame_trace_core;}\n'
            'u32 time_us_32(){return u32('+clock+');}\n'+declaration+'\n'+methods+'}\n')
