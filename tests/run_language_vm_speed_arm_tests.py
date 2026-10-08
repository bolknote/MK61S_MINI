#!/usr/bin/env python3
"""Matched generic VM ARM instruction gate; no physical latency/heap claim."""
import argparse,json,struct,subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_C1_C0_2,UC_ARM_REG_FPEXC,UC_ARM_REG_SP,
                              UC_ARM_REG_LR,UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_PC)
ROOT=Path(__file__).resolve().parents[1]
CASES={
 'basic_integer':('basic','10 S=0;FOR I=1 TO 500;B=I MOD 128;C=INT(I/128);@(B)=B+C;S=S+@(B);NEXT I\n20 A=S\n'),
 'basic_mixed':('basic','10 A=0;FOR I=1 TO 500;A=A+.1;NEXT I\n'),
 'basic_branches':('basic','10 A=0\n20 A=A+1\n30 IF A<500 GOTO 20\n'),
 'basic_subroutines':('basic','10 A=0;FOR I=1 TO 500;GOSUB 100;NEXT I;END\n100 A=A+I;RETURN\n'),
 'basic_wide':('basic','10 A=281474976710655;FOR I=1 TO 500;B=INT(A/536870912);C=A MOD 65536;NEXT I\n20 A=B+C\n'),
 'basic_decimals':('basic','10 A=0;FOR I=1 TO 500;A=A+.1+.2+.3+.4+.5+.6+.7;NEXT I\n'),
 'basic_expressions':('basic','10 A=0;FOR I=1 TO 500;B=(I+3)*(I-2);C=INT(B/16);A=A+C-B MOD 17;NEXT I\n'),
 'focal_integer':('focal','1.10 S A=0\n1.20 F I=1,500;S A=A+I\n1.30 E\n'),
 'focal_mixed':('focal','1.10 S A=0\n1.20 F I=1,500;S A=A+.1\n1.30 E\n'),
 'focal_subroutines':('focal','1.10 S A=0\n1.20 F I=1,500;D 2\n1.30 E\n2.10 S A=A+I\n')
}
def run(command):
 p=subprocess.run([str(x) for x in command],text=True,capture_output=True)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return p.stdout
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--baseline-source',type=Path,required=True)
 ap.add_argument('--candidate-source',type=Path,default=ROOT)
 ap.add_argument('--arm-toolchain-bin',type=Path,required=True)
 ap.add_argument('--output-dir',type=Path,required=True)
 args=ap.parse_args();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
 rows=[]
 for variant,root in (('baseline',args.baseline_source.resolve()),('candidate',args.candidate_source.resolve())):
  work=out/variant;work.mkdir(exist_ok=True);target=work/'vm.elf';probe=work/'probe'
  run([args.arm_toolchain_bin/'arm-none-eabi-g++','-std=c++17','-Os','-mcpu=cortex-m4','-mthumb',
       '-mfpu=fpv4-sp-d16','-mfloat-abi=hard','-fno-builtin','-ffunction-sections','-fdata-sections',
       '-nostdlib','-Wl,-Ttext=0x10000,-e,bench,--gc-sections','-I'+str(root/'code'),
       ROOT/'tests/language_vm_speed_arm_probe.cpp',root/'code/language_vm.cpp',root/'code/language_bytecode.cpp',
       '-Wl,--start-group','-lc','-lgcc','-Wl,--end-group','-o',target])
  run(['clang++','-std=c++17','-O2','-I'+str(root/'code'),ROOT/'tools/language_vm_probe.cpp',
       root/'code/language_vm.cpp',root/'code/language_bytecode.cpp',root/'code/zx0_encode.cpp','-o',probe])
  with target.open('rb') as stream:
   elf=ELFFile(stream)
   segments=[(s['p_vaddr'],s.data()) for s in elf.iter_segments() if s['p_type']=='PT_LOAD']
   symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
   rom=sum(s['sh_size'] for s in elf.iter_sections() if s['sh_flags']&2 and not s['sh_flags']&1)
  for name,(language,source) in CASES.items():
   text=work/(name+'.txt');image=work/(name+'.lbv');text.write_text(source)
   run([probe,language,text,image]);data=image.read_bytes()
   uc=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);uc.mem_map(0,0x100000);uc.mem_map(0x20000000,0x20000)
   for address,chunk in segments:uc.mem_write(address,chunk)
   uc.reg_write(UC_ARM_REG_C1_C0_2,0xF00000);uc.reg_write(UC_ARM_REG_FPEXC,0x40000000)
   uc.mem_write(0x20000000,data);uc.reg_write(UC_ARM_REG_SP,0x2001F000);uc.reg_write(UC_ARM_REG_LR,0xF0001)
   uc.reg_write(UC_ARM_REG_R0,0x20000000);uc.reg_write(UC_ARM_REG_R1,len(data));uc.reg_write(UC_ARM_REG_R2,0x20004000)
   count=[0]
   def hook(*unused):count[0]+=1
   uc.hook_add(UC_HOOK_CODE,hook);uc.emu_start(symbols['bench']|1,0xF0000,count=20000000)
   assert uc.reg_read(UC_ARM_REG_PC)==0xF0000,(variant,name)
   value=struct.unpack('<d',uc.mem_read(0x20004000,8))[0];error=uc.reg_read(UC_ARM_REG_R0)
   assert not error,(variant,name,error)
   rows.append({'variant':variant,'case':name,'instructions':count[0],'value':value,'image_bytes':len(data),'rom_bytes':rom})
   print(variant,name,count[0],value,flush=True)
 comparisons={}
 for name in CASES:
  old,new=[next(r for r in rows if r['variant']==v and r['case']==name) for v in ('baseline','candidate')]
  assert old['value']==new['value'],(name,old,new)
  assert new['instructions']<old['instructions'],(name,old,new)
  comparisons[name]={'arm_instruction_ratio':old['instructions']/new['instructions'],
                     'instruction_change_percent':100*(new['instructions']/old['instructions']-1),
                     'image_delta':new['image_bytes']-old['image_bytes']}
 result={'status':'PASS','runs':rows,'comparisons':comparisons,
         'note':'ARM instruction counts incl initial validation, not Cortex cycles/device time; no IO or APP loading in this gate.'}
 (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(comparisons,indent=2))
if __name__=='__main__':main()
