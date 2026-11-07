"""All modes, complete visible state and stop/resume on the real MK-61 core."""
import ctypes as C
from decimal import Decimal
import hashlib
from pathlib import Path
import subprocess

from emulator import decimal_parts,read_decimal
from full_isa_protocol import hex_code,REGISTERS
from tasks import BUILD

ROOT=BUILD/'full-isa-v1'
HERE=Path(__file__).parent
REPO=HERE.parents[1]
ANGLES={'RAD':10,'DEG':11,'GRAD':12}
STACK=['X1','X','Y','Z','T']


def build():
    ROOT.mkdir(exist_ok=True);out=ROOT/'libfullisa.so'
    core=ROOT/'core-source'if(ROOT/'core-source/mk61emu_core.cpp').exists()else REPO/'code'
    files=[HERE/'full_isa_bridge.cpp',HERE/'core_bridge.cpp',core/'mk61emu_core.cpp',
      *sorted(core.rglob('*.h')),*sorted(core.rglob('*.hpp'))]
    digest=hashlib.sha256(b''.join(p.read_bytes()for p in files)).hexdigest();stamp=out.with_suffix('.sha256')
    if not out.exists()or not stamp.exists()or stamp.read_text().strip()!=digest:
        subprocess.run(['c++','-std=c++17','-O2','-fPIC','-shared','-DMK61_CORE_STANDALONE=1','-DMK61_CORE_HOT_TABLES_IN_SRAM=0',
          '-I',str(core),str(HERE/'full_isa_bridge.cpp'),str(core/'mk61emu_core.cpp'),'-o',str(out)],check=True,capture_output=True)
        stamp.write_text(digest+'\n')
    return out


class FullVM:
    """One core per process; save/restore isolates cases and tool continuations."""
    def __init__(self):
        self.lib=C.CDLL(str(build()));l=self.lib
        l.fi_reset.argtypes=[C.c_uint];l.mk_load.argtypes=[C.POINTER(C.c_ubyte),C.c_uint]
        l.mk_set_register.argtypes=[C.c_uint,C.POINTER(C.c_ubyte)]
        l.mk_set_stack.argtypes=[C.c_uint,C.c_int,C.c_char_p,C.c_int]
        l.mk_read_stack.argtypes=[C.c_uint,C.c_char_p];l.mk_read_register.argtypes=[C.c_uint,C.c_char_p]
        l.fi_save.argtypes=[C.POINTER(C.c_ubyte),C.c_uint];l.fi_restore.argtypes=[C.POINTER(C.c_ubyte),C.c_uint]
        l.mk_trace_x.argtypes=[C.c_uint,C.c_char_p];self.context_bytes=l.mk_context_bytes()

    def inputs(self,values):
        for name,value in values.items():
            negative,digits,exponent=decimal_parts(value);name=name.upper()
            if name in STACK:
                ok=self.lib.mk_set_stack(STACK.index(name),int(negative),digits.encode(),exponent)
            elif name in REGISTERS:
                e=exponent if exponent>=0 else 100+exponent
                packed=[4|(128 if negative else 0)|(64 if exponent<0 else 0),(e//10)*16+e%10,
                  *[(int(digits[i:i+2])//10)*16+int(digits[i:i+2])%10 for i in range(0,8,2)]]
                ok=self.lib.mk_set_register(int(name[1:],16),(C.c_ubyte*len(packed))(*packed))
            else:raise ValueError('Unknown register '+name)
            if ok!=0:raise ValueError('Cannot set register '+name)

    def save(self):
        out=(C.c_ubyte*self.context_bytes)();assert self.lib.fi_save(out,len(out))==0
        return bytes(out)

    def restore(self,state):
        data=(C.c_ubyte*len(state)).from_buffer_copy(state);assert self.lib.fi_restore(data,len(data))==0

    def execute(self,code,values=None,*,angle='RAD',context=None,max_commands=256,max_frames=4096):
        if context is None:
            hex_code(code);assert self.lib.fi_reset(ANGLES[angle])==0
            data=(C.c_ubyte*len(code))(*code);assert self.lib.mk_load(data,len(code))==0
        else:self.restore(context)
        self.inputs(values or{});status=self.lib.mk_run(max_commands,max_frames)
        raw={};numeric={}
        for name in [*STACK,*REGISTERS]:
            out=C.create_string_buffer(64)
            if name in STACK:self.lib.mk_read_stack(STACK.index(name),out)
            else:self.lib.mk_read_register(int(name[1:],16),out)
            text=out.value.decode('ascii',errors='replace').strip();raw[name]=text
            try:numeric[name]=read_decimal(out.value)
            except (ValueError,ArithmeticError):numeric[name]=None
        trace=[{'pc':self.lib.mk_trace_address(i),'opcode':self.lib.mk_trace_opcode(i)}for i in range(self.lib.mk_trace_size())]
        return {'status':{0:'stopped',1:'limit',2:'error',-1:'internal_error'}[status],
          'pc':self.lib.mk_pc(),'raw':raw,'numeric':numeric,'trace':trace},self.save()


def state_match(actual,expected,*,names=None,check_pc=False,raw=False):
    if actual['status']!=expected['status']:return False
    if check_pc and actual['pc']!=expected['pc']:return False
    names=names or[*STACK,*REGISTERS]
    for name in names:
        a=actual['numeric'][name];b=expected['numeric'][name]
        if raw or a is None or b is None:
            if actual['raw'][name]!=expected['raw'][name]:return False
        else:
            a=Decimal(a);b=Decimal(b)
            if not a.is_finite()or abs(a-b)>max(Decimal('0.000002'),abs(b)*Decimal('0.000002')):return False
    return True


def check_task(vm,code,task,*,public=False):
    cases=task['public_tests']+( []if public else task['hidden_tests']);details=[]
    for case in cases:
        context=None;ok=True;segments=[]
        for segment in case['segments']:
            actual,context=vm.execute(code,segment['inputs'],angle=task['angle'],context=context,
              max_commands=task.get('max_commands',256),max_frames=task.get('max_frames',4096))
            names=task.get('check_names')
            if names is not None:names=list(dict.fromkeys([*names,*REGISTERS]))
            passed=state_match(actual,segment['expected'],names=names,check_pc=task.get('check_pc',False),raw=task.get('raw_compare',False))
            ok &= passed;segments.append({'pass':passed,'actual':actual})
        details.append({'pass':bool(ok),'segments':segments})
    return {'pass':bool(details)and all(x['pass']for x in details),'details':details}
