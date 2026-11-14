#!/usr/bin/env python3
"""HOST-only: RAM modules and a Pico APP pinned to a verified resident ELF."""
from pathlib import Path
import argparse,hashlib,json,re,struct,subprocess,sys,zlib
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'sdk/coproc'))
from elf32 import ELF

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--output',type=Path,default=ROOT/'.build/picocalc-fastlink-20261111/kit-017')
 ap.add_argument('--cycles',type=int,choices=range(1,101),default=1)
 ap.add_argument('--nrz4',action='store_true')
 ap.add_argument('--reference-packer',action='store_true',help='Diagnostic A/B only: original hardware016 packing algorithm')
 ap.add_argument('--resident',type=Path,default=ROOT/'.build/mk61ai/lut8-hybrid-20261111/firmware')
 ap.add_argument('--toolchain',type=Path,default=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin'))
 ap.add_argument('--pico-sdk',type=Path,default=ROOT/'.build/picocalc-deps/pico-sdk')
 a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 assert not a.reference_packer or a.nrz4
 (out/'experiment_config.h').write_text(('#define FL_NRZ4_ONLY 1\n'if a.nrz4 else'')+
  ('#define FL_NRZ4_REFERENCE 1\n'if a.reference_packer else'')+'#define FL_CYCLES %uu\n'%a.cycles)
 assert out.is_relative_to(ROOT/'.build')
 tool=lambda name:str(a.toolchain/('arm-none-eabi-'+name))
 def run(cmd,log):
  with (out/log).open('w') as f:subprocess.run(list(map(str,cmd)),check=True,stdout=f,stderr=subprocess.STDOUT)
 modules={}
 for stem in ('identity','module','legacy_module'):
  elf=out/(stem+'.elf');binary=out/(stem+'.bin');package=out/(stem+'.s3m')
  flags=['-mcpu=cortex-m3','-mthumb','-mfloat-abi=soft','-std=c11','-Os','-g',
   '-mword-relocations','-ffreestanding','-fno-builtin','-fno-common','-fno-stack-protector',
   '-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fsection-anchors','-ffunction-sections',
   '-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-I'+str(ROOT/'sdk/coproc'),'-I'+str(HERE),'-I'+str(out)]
  source=HERE/('fixtures/'+stem+'.c'if stem=='legacy_module'else stem+'.c')
  run([tool('gcc'),*flags,'-nostdlib',source,'-Wl,-T,'+str(ROOT/'sdk/coproc/module.ld'),
    '-Wl,--emit-relocs,--gc-sections,-Map='+str(out/(stem+'.map')),'-o',elf],stem+'-build.log')
  subprocess.run([tool('objcopy'),'-O','binary','-j','.image',str(elf),str(binary)],check=True)
  e=ELF(elf);image=binary.read_bytes();memory=e.symbols['__memory_end']['value']-0x20000000
  offsets=[]
  for at,kind in e.relocations():
   if kind==2:offsets.append(at-0x20000000)
   else:assert kind in (3,10,30,42),kind
  offsets=sorted(set(offsets));assert len(offsets)<=64 and memory<=6144
  for at in offsets:
   assert at%4==0 and at+4<=len(image) and 0x20000000<=struct.unpack_from('<I',image,at)[0]<=0x20000000+memory
  for name,s in e.symbols.items():assert s['index']!=0,name
  payload=image+b''.join(struct.pack('<I',x) for x in offsets)
  words=[0x314d3353,1,64,64+len(payload),len(image),memory-len(image),e.entry-0x20000000,len(offsets),
   24,512,512,2000,zlib.crc32(payload),0,0x70301]
  header=struct.pack('<15I',*words)
  package.write_bytes(header+struct.pack('<I',zlib.crc32(header))+payload)
  (out/(stem+'-disassembly.txt')).write_bytes(subprocess.check_output([tool('objdump'),'-d',str(elf)]))
  modules[stem]=dict(sha256=sha(package),image_bytes=len(image),memory_bytes=memory,
   bss_bytes=memory-len(image),package_bytes=package.stat().st_size,relocations=offsets)
 arrays=[]
 for stem,label in (('identity','identity'),('module','link')):
  data=(out/(stem+'.s3m')).read_bytes()
  arrays.append('static const uint8_t '+label+'_package[]={'+','.join(str(v) for v in data)+'};\n')
 (out/'packages.h').write_text(''.join(arrays))
 native=a.resident/'mk61s-picocalc-pico-h.elf';elf=ELF(native)
 manifest=json.loads((a.resident/'manifest.json').read_text())
 verified={('7c38c634','8a17554e'):'75ef19a5237b0ed25357424e1fd31da2aa64c69fa98683b4300dc7f553ffce16',
  ('c99de0af','528f4874'):'4139bcb17c802288c93c2ab6efa5248f996166874ffb0b2b7bf20f8a18c88bb0'}
 assert sha(native)==verified[(manifest['build_id'],manifest['firmware_integrity']['crc32'])]
 names={'DMA_CLAIM':'dma_claim_unused_channel','DMA_UNCLAIM':'dma_channel_unclaim',
  'PIO_CLAIM':'pio_claim_unused_sm','PIO_UNCLAIM':'pio_sm_unclaim','PIO_ADD':'pio_add_program',
  'PIO_REMOVE':'pio_remove_program','PIO_INIT':'pio_sm_init','PIO_PINDIRS':'pio_sm_set_consecutive_pindirs',
  'PIO_CAN_ADD':'pio_can_add_program'}
 def rom(at,n):
  for seg in elf.segments:
   base=seg['address']
   if base<=at and at+n<=base+len(seg['data']):return seg['data'][at-base:at-base+n]
  raise ValueError(hex(at))
 probes=[];definitions=['#define FL_EXPECTED_BUILD_STRING "'+manifest['build_id'].upper()+'"\n']
 register_header=a.pico_sdk.resolve()/'src/rp2040/hardware_regs/include/hardware/regs/pio.h'
 register_source=register_header.read_text();registers={}
 for label in ('PIO_IRQ0_INTE','PIO_IRQ0_INTF','PIO_IRQ1_INTE','PIO_IRQ1_INTF'):
  matches=re.findall(r'^#define '+label+r'_OFFSET _u\((0x[0-9a-f]+)\)$',register_source,re.M)
  assert len(matches)==1,label
  registers[label]=int(matches[0],16);definitions.append('#define FL_REG_'+label+' '+matches[0]+'u\n')
 i2c_header=register_header.with_name('i2c.h');i2c_source=i2c_header.read_text();i2c_registers={}
 reset_header=register_header.with_name('resets.h')
 reset_matches=re.findall(r'^#define RESETS_RESET_I2C1_BITS\s+_u\((0x[0-9a-f]+)\)$',reset_header.read_text(),re.M)
 assert reset_matches==['0x00000010'];definitions.append('#define FL_RESET_I2C1_BITS '+reset_matches[0]+'u\n')
 for name in ('IC_INTR_MASK','IC_TXFLR','IC_RXFLR','IC_STATUS','IC_RAW_INTR_STAT','IC_ENABLE','IC_ENABLE_STATUS','IC_TX_ABRT_SOURCE'):
  matches=re.findall(r'^#define I2C_'+name+r'_OFFSET _u\((0x[0-9a-f]+)\)$',i2c_source,re.M)
  assert len(matches)==1,name
  i2c_registers[name]=int(matches[0],16);definitions.append('#define FL_REG_I2C_'+name+' '+matches[0]+'u\n')
 layout=subprocess.check_output([tool('gdb'),'-batch','-ex','file '+str(native),
  '-ex','ptype /o picocalc::Keyboard',
  '-ex','p/x (unsigned)&((picocalc::Keyboard *)0)->pending_',
  '-ex','p/x (unsigned)&((picocalc::Keyboard *)0)->io_phase_',
  '-ex','p sizeof(picocalc::Keyboard)',
  '-ex','p/x (unsigned)&((mk61_app_api *)0)->service'],text=True)
 (out/'keyboard-layout.txt').write_text(layout)
 fields=re.findall(r'^\$\d+ = (0x[0-9a-f]+|[0-9]+)$',layout,re.M)
 assert list(map(lambda v:int(v,0),fields))==[1,3,56,16]
 keyboard=elf.symbols['_ZN12_GLOBAL__N_18keyboardE'];assert keyboard['size']==56
 definitions.append('#define FL_NATIVE_KBD_PENDING 0x%08Xu\n'%(keyboard['value']+1))
 definitions.append('#define FL_NATIVE_KBD_PHASE 0x%08Xu\n'%(keyboard['value']+3))
 health_layout=subprocess.check_output([tool('gdb'),'-batch','-ex','file '+str(native),
  '-ex',"ptype /o 'picocalc::io_worker::(anonymous namespace)::I2cJob'",
  '-ex',"p/x (unsigned)&'picocalc::io_worker::(anonymous namespace)::i2c'.stage",
  '-ex',"p/x (unsigned)&'picocalc::io_worker::(anonymous namespace)::i2c'.result",
  '-ex','p/x (unsigned)&((picocalc::Keyboard *)0)->errors_',
  '-ex','p/x (unsigned)&((picocalc::WorkerDeadlineTrace *)0)->resets'],text=True)
 (out/'native-health-layout.txt').write_text(health_layout)
 fields=re.findall(r'^\$\d+ = (0x[0-9a-f]+|[0-9]+)$',health_layout,re.M)
 job=elf.symbols['_ZN8picocalc9io_worker12_GLOBAL__N_13i2cE']
 trace=elf.symbols['_ZN8picocalc9io_worker12_GLOBAL__N_114deadline_traceE']
 assert job['size']==20 and trace['size']==16
 assert [int(v,0)for v in fields]==[job['value'],job['value']+16,44,4]
 health_addresses={'I2C_STAGE':job['value'],'I2C_RESULT':job['value']+16,
  'I2C_RESETS':trace['value']+4,'KBD_ERRORS':keyboard['value']+44,'KBD_ONLINE':keyboard['value']}
 for label,name in [('I2C_TIMEOUTS','_ZN8picocalc9io_worker12_GLOBAL__N_112i2c_timeoutsE'),
                    ('I2C_ABORTS','_ZN8picocalc9io_worker12_GLOBAL__N_110i2c_abortsE')]:
  symbol=elf.symbols[name];assert symbol['size']==4;health_addresses[label]=symbol['value']
 for name,address in health_addresses.items():
  definitions.append('#define FL_NATIVE_'+name+' 0x%08Xu\n'%address)
 for label,name in names.items():
  at=elf.symbols[name]['value'];assert at&1 and 0x10000000<at<0x101c0000
  definitions.append('#define FL_'+label+' 0x%08Xu\n'%at)
  probes.append((at&~1,rom(at&~1,16)))
 footer=0x10000000+manifest['firmware_integrity']['footer_offset'];probes.append((footer,rom(footer,32)))
 checks=[]
 for i,(at,data) in enumerate(probes):
  definitions.append('static const uint8_t fl_pin_%u[]={%s};\n'%(i,','.join(str(v) for v in data)))
  checks.append('for(unsigned j=0;j<sizeof(fl_pin_%u);++j)if(*(volatile const uint8_t *)(uintptr_t)(0x%08Xu+j)!=fl_pin_%u[j])return 0;'%(i,at,i))
 (out/'native_pins.h').write_text(''.join(definitions)+'static int fl_native_matches(void){'+''.join(checks)+'return 1;}\n')
 app=out/'app'
 run([sys.executable,ROOT/'tools/apps/portable/build_portable_app.py','--target','picocalc-pico-h',
  '--shared-runtime','--name','FASTLINK','--include',HERE,'--include',out,'--include',ROOT/'sdk/coproc',
  '--source',HERE/'pico.c','--source',ROOT/'sdk/coproc/stm3_client.c','--source',ROOT/'sdk/coproc/pico_uart1.c',
  '--arm-toolchain-bin',a.toolchain,'--output-dir',app],'pico-build.log')
 result=dict(status='COMPILED_NOT_HARDWARE_TESTED',run_cycles=a.cycles,nrz4=a.nrz4,
  nrz4_packer='reference'if a.reference_packer else'frames'if a.nrz4 else None,
  pico_build=manifest['build_id'].upper(),pico_crc=manifest['firmware_integrity']['crc32'].upper(),
  resident_elf_path=str(native.resolve()),resident_elf_sha256=sha(native),pico_flash_bytes=manifest['flash_bytes'],pico_hz=125000000,m3_hz=72000000,
  modules=modules,app=json.loads((app/'FASTLINK.json').read_text()),
  app_sha256=sha(app/'FASTLINK.APP'),source_pins={str(p.relative_to(ROOT)):sha(p) for p in HERE.rglob('*') if p.is_file()and'__pycache__'not in p.parts},
  native_resource_functions={k:hex(elf.symbols[v]['value']) for k,v in names.items()},
  register_header=dict(path=str(register_header),sha256=sha(register_header),values=registers),
  i2c_header=dict(path=str(i2c_header),sha256=sha(i2c_header),values=i2c_registers),
  reset_header=dict(path=str(reset_header),sha256=sha(reset_header),i2c1_bits=16),
  native_keyboard=dict(address=keyboard['value'],size=56,pending_offset=1,phase_offset=3,service_api_offset=16,layout_sha256=sha(out/'keyboard-layout.txt')),
  native_health=dict(addresses=health_addresses,layout_sha256=sha(out/'native-health-layout.txt')),
  flash_writes=0,hardware_timing_measured=False)
 (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
