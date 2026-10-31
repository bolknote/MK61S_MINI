"""Mixed SRAM/Flash/public-runtime report proof for the frozen M4 shadow."""
import json
from pathlib import Path
import statistics
import struct
import sys
from types import SimpleNamespace
from relocation import geometry
from session import Hold,sha
import run as bench
from firmware import ORIGINAL_SHA
from check_stm32_vectors import ElfImage

ROOT=Path(__file__).resolve().parents[2]
BUILD='2CC0B4D1'
PREFIX_SHA='0931d4d63125cb8f7bc64dfb0e937a4c786c6105e52dd87dd2856d25e739f783'
RESIDENT_ELF_SHA='e091d2be318d229d1023466b1ccb50ee2b1188f0c0e2cf4f9eb1ad65b02bda26'
FULL_SHA='41b59c1f927dc8cfc4d91d19db0bc902cce2d5fcfe774a56bbe011f85b948c10'
PAYLOAD_SHA='0cf9b2827753dc82b319305d705477149d70d6a3acaaeebd3d216df4ff8e3d0e'
APPS=(('/MCHR-X01','635338b5450584204291874373fdaaab3d41312fb067c20169a87b57c09dda06',False,'sram'),
      ('/MCHR-X02','4cd9c5fdc7aabf4890cc923cbea6b984a7d184b78aeab9a2812bf1c87b8010d6',True,'sram'),
      ('/MCHR-X03','c3408339943a0734a420f1db5e35829f5ad0b6d97a08e52bc28d0c944f0a2b94',False,'flash'))
SYMBOLS=['baseline','libc_search','byte_search','own4','own16','own64','pair16','balanced16','pair64','balanced64','dsp16','dsp32','compact8','memchr','@resident_memchr','indirect_search']
NAMES=['baseline','libc','byte','own4','own16','own64','pair16','balanced16','pair64','balanced64','dsp16','dsp32','compact8','sdk','public_body','public_veneer']

def cases(corpus):
    result=[]
    for source in corpus.sources:
        values=vars(corpus).copy();values.update(cpu='m4',sources=[source],values=corpus.flash_values if source else corpus.values)
        result+=bench.cases(SimpleNamespace(**values))
    return result

def dependencies(entry):
    paths={Path(__file__).resolve(),Path(entry).resolve(),Path(bench.old.__file__).resolve()}
    for name,module in list(sys.modules.items()):
        if name=='__main__':continue
        value=getattr(module,'__file__',None)
        if value:
            path=Path(value).resolve()
            if path.suffix=='.py' and ROOT in path.parents:paths.add(path)
    return {str(path.relative_to(ROOT)):sha(path.read_bytes()) for path in sorted(paths)}

def verify_images(plan):
    original=Path(plan['original_reference']).read_bytes();prefix=Path(plan['sealed_prefix']).read_bytes();payload=Path(plan['payload']).read_bytes()
    if len(original)!=524288 or sha(original)!=ORIGINAL_SHA or sha(prefix)!=PREFIX_SHA or sha(payload)!=PAYLOAD_SHA:raise Hold('Frozen original/prefix/payload differs')
    if len(prefix)!=376148 or len(payload)!=8208 or original[0x62000:0x62000+8208]!=b'\xff'*8208:raise Hold('Frozen Flash extension is not unused')
    candidate=bytearray(original);candidate[:len(prefix)]=prefix;candidate[0x62000:0x62000+8208]=payload
    if sha(candidate)!=FULL_SHA or Path(plan['candidate']).read_bytes()!=candidate:raise Hold('Full candidate is not the exact derived image')
    resident=ElfImage(plan['resident_elf'])
    if sha(resident.data)!=RESIDENT_ELF_SHA:raise Hold('Sealed resident ELF differs')
    reconstructed=bytearray(b'\xff'*len(prefix))
    for kind,at,_vaddr,paddr,size,_mem,_flags,_align in resident.segments:
        if kind!=1 or not size or not 0x08000000<=paddr<0x08080000:continue
        offset=paddr-0x08000000
        if offset+size>len(prefix):raise Hold('Resident ELF load outside sealed prefix')
        reconstructed[offset:offset+size]=resident.data[at:at+size]
    if reconstructed!=prefix:raise Hold('Resident ELF does not reconstruct every sealed BIN byte')
    if (resident.symbols['__mk61_dynamic_begin'],resident.symbols['__mk61_dynamic_end'])!=(0x200053f8,0x2001bf00):raise Hold('Resident ELF SRAM arena differs')
    services=resident.symbols['_ZZN15loadable_module12app_servicesEvE3api']
    header=struct.unpack_from('<8I',prefix,services-0x08000000)
    if services!=0x0805459c or header[:2]!=(0x31535953,0x00200002) or header[6:]!=(0x08051e60,27):raise Hold('Resident BIN provider fields differ')
    entries=struct.unpack_from('<27I',prefix,header[6]-0x08000000)
    target=resident.symbols['memchr']|1;size=resident.sizes['memchr'];offset=(target&~1)-0x08000000
    body=prefix[offset:offset+size]
    if target!=0x08050a75 or entries[26]!=target or size!=450 or sha(body)!='bd4502b3460e1d7c13ffdfe257d0106099e36111433ba9b0e1565cc5172de521':raise Hold('Resident BIN memchr body differs')
    runtime=json.loads(Path(plan['runtime_proof']).read_text());service=runtime['services']
    if runtime['build']!=BUILD or runtime['static_end']!='0x200053f8' or service['struct_size']!=32 or service['runtime_count']!=27:raise Hold('Resident runtime proof differs')
    if service['memchr']['address']!='0x8050a75' or service['table']!='0x8051e60':raise Hold('Resident entry/table differs')
    if service['address']!=hex(services) or service['entries']!=list(map(hex,entries)) or service['memchr']!=dict(address=hex(target),bytes=size,sha256=sha(body)):raise Hold('JSON runtime proof disagrees with sealed BIN/ELF')
    layout=json.loads(Path(plan['payload_layout']).read_text());kernels=ElfImage(plan['payload_elf'])
    # Payload builder installs .text only, omitting the unused ARM unwind
    # index. Compare the complete installed executable section, not that index.
    text=kernels.named_sections['.text'];offset=text[3]-0x08062000
    if offset!=64 or text[5]!=layout['code_bytes'] or payload[offset:offset+text[5]]!=kernels.bytes_at(text):raise Hold('Payload ELF code differs from installed payload bytes')
    for name,item in layout['functions'].items():
        offset=(item['address']&~1)-0x08062000
        if offset<64 or offset+item['bytes']>4096 or sha(payload[offset:offset+item['bytes']])!=item['sha256']:raise Hold('Payload layout body disagrees with installed bytes: '+name)
    return runtime

def proof(plan,row):
    manifest=json.loads(Path(row['manifest']).read_text())
    if (manifest['directory'],manifest['shared'],manifest['app_sha256'],manifest['cpu'])!=(row['directory'],row['shared'],row['app_sha256'],'m4'):raise Hold('Wide APP manifest identity differs')
    if manifest['symbols']!=SYMBOLS or manifest['report_version']!=4 or manifest['rows_per_chunk']!=7 or manifest['fp_base']!=36:raise Hold('Wide report contract differs')
    if manifest['expected_runtime_count']!=27 or manifest['expected_services_size']!=32 or manifest['placement']!=row['placement']:raise Hold('Wide provider/placement differs')
    names=[n if n!='@resident_memchr' else 'byte_search' for n in SYMBOLS]
    args=(row['app'],row['elf'],row['raw_image'],plan['payload_elf'],row['kernel_layout'],0x200053f8,0x2001bf00)
    result=geometry(*args,names=names)
    layout=json.loads(Path(plan['payload_layout']).read_text())
    elf=ElfImage(plan['payload_elf'])
    if layout['elf_sha256']!=sha(Path(plan['payload_elf']).read_bytes()):raise Hold('Payload ELF identity changed')
    for name in SYMBOLS[:13]:
        item=layout['functions'][name]
        address=item['address']&~1
        if item['address']!=(elf.symbols[name]|1) or not 0x08062040<=address or address+item['bytes']>0x08063000:raise Hold('Payload entry is outside its frozen code region')
    if row['placement']=='flash':
        for index,name in enumerate(SYMBOLS[:13]):result['pointers'][index]=layout['functions'][name]['address']
    result['pointers'][14]=0x08050a75
    cached=geometry(*args,names=('mk61_memchr_fallback' if row['shared'] else 'memchr',))
    result['sdk_local_body']=cached['bodies'];result['sdk_cached_target']=0x08050a75 if row['shared'] else cached['pointers'][0]
    result['runtime_table']=0x08051e60;result['payload_crc32']=int(layout['crc32'],16)
    return result

def validator(inputs,bounded,full):
    length=256+500*len(inputs);expected=tuple(map(tuple,inputs))
    def recognized(raw):
        if len(raw)!=length:return False
        h=struct.unpack_from('<64I',raw)
        if h[:5]!=(0x4d435250,4,16,len(inputs),7) or h[15]!=96000000:return False
        # Exact known diagnostic outcomes before any payload entry executes.
        if h[6] and h[54] in (0,1) and h[14]==0 and not any(raw[256:]) and not any(h[36:52]):
            empty=not any(h[7:11]) and h[5]==0 and h[13]==0 and not any(h[26:28]) and not any(h[33:36])
            known=(h[54]==0 and h[24]!=0x9f8f7ded and h[25]==0) or (h[54]==1 and h[24]==0x9f8f7ded and h[25]!=bounded['payload_crc32'])
            return h[6]==1 and empty and known
        if h[24]!=0x9f8f7ded or h[25]!=bounded['payload_crc32'] or h[26:28]!=(4,27):return False
        if h[13]!=0x08050a75 or h[34]!=32 or h[35]!=bounded['runtime_table'] or h[36:52]!=tuple(bounded['pointers']):return False
        if h[33]!=bounded['sdk_cached_target']:return False
        if h[6] and h[54] in (3,4) and h[14]==0 and not any(raw[256:]):return h[7]<16 and h[8]<=4096 and h[9]<=7
        if h[6] or h[54]!=6 or h[5]!=16*(len(inputs)+1)+(193600 if full else 0) or h[14]<19200000:return False
        return all(struct.unpack_from('<6I',raw,256+i*500)==values for i,values in enumerate(expected))
    return recognized

def decode(raw,inputs,bounded,full):
    if not validator(inputs,bounded,full)(raw):raise Hold('Wide report differs from frozen mixed-code proof')
    h=struct.unpack_from('<64I',raw)
    if h[6]:raise Hold('Wide hardware correctness failed: '+repr(h[:56]))
    rows=[]
    for index,values in enumerate(inputs):
        words=struct.unpack_from('<125I',raw,256+index*500);control=words[6:13];timings={}
        for f,name in enumerate(NAMES):
            samples=words[13+f*7:20+f*7];cycles=[(sample-empty)/values[3] for sample,empty in zip(samples,control)]
            timings[name]=dict(raw=list(samples),paired_cycles=cycles,median_cycles=statistics.median(cycles))
        rows.append(dict(size=values[0],offset=values[1],value=values[2],loops=values[3],source=values[4],mode=values[5],
            prefix_bytes=bench.prefix(values[0],values[1],values[2],values[4],values[5]),control=list(control),timings=timings))
    return dict(checks=h[5],clock=h[15],rows=rows,public_runtime_present=True,runtime_count=27,services_size=32,
        sdk_first_call_raw_cycles=h[32],sdk_cached_target=hex(h[33]),flash_acr=hex(h[11]),
        public_body='Resident function pointer hoisted outside the timed loop',public_veneer='Actual public table load and dispatch on every call',
        addresses={n:hex(a) for n,a in zip(NAMES,h[36:52])})
