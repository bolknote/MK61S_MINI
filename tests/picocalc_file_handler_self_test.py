#!/usr/bin/env python3
"""Exercise the production handler lookup/dispatch against an in-memory SD."""
import os
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'ports/picocalc/native_app.cpp').read_text()
helpers=source[source.index('bool join(const char *directory'):source.index('} // namespace')]
dispatch=source[source.index('u8 Services::run_handled('):source.index('u8 Services::run_native(')]
with tempfile.TemporaryDirectory(prefix='picocalc-file-handler-') as directory:
    work=Path(directory)
    (work/'picocalc_file_handler_production.inc').write_text(helpers+'\n'+dispatch)
    cmd=[os.environ.get('CXX','clang++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-DMK61_CORE_STANDALONE=1',
         '-I'+str(work),'-I'+str(ROOT/'code'),'-I'+str(ROOT/'ports/picocalc')]
    if os.environ.get('MK61_TEST_SANITIZERS')=='1':
        cmd+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
    subprocess.run(cmd+[str(ROOT/'tests/picocalc_file_handler_self_test.cpp'),
                        str(ROOT/'code/loadable_module_format.cpp'),str(ROOT/'code/zx0.cpp'),
                        '-o',str(work/'test')],check=True)
    subprocess.run([str(work/'test')],check=True)
