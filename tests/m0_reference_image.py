"""Join an independently linked diagnostic reference to a sealed production ELF.

Cross-memory veneers can depend on the complete link symbol table. Keeping
the production link intact preserves their addresses, code and SRAM initializer.
The footer and two non-mathematical image-bound literals must describe the
joined image; all other original flash bytes and every RAM initializer remain.
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

from check_stm32_vectors import ElfImage
from check_m0_math_layout import symbol_types
from build_picocalc import compiler_bin
from seal_picocalc import seal, verify, BASE, FOOTER

REFERENCE_BASE=0x10180000
TARGET='mk61s-picocalc-pico-h'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def append_reference_elf(original,blob,exported,image,footer_offset):
    """Append reference metadata without rewriting existing LOAD segments."""
    header=struct.Struct('<16sHHIIIIIHHHHHH')
    sh=struct.Struct('<10I');ph=struct.Struct('<8I');sym=struct.Struct('<IIIBBH')
    h=list(header.unpack_from(original.data));assert h[9]==ph.size and h[11]==sh.size
    sections=[list(s) for s in original.sections];new_index=len(sections)
    tables=[i for i,s in enumerate(sections) if s[1]==2];assert len(tables)==1
    symbols_index=tables[0];strings_index=sections[symbols_index][6];names_index=h[13]
    names=bytearray(original.bytes_at(sections[names_index]))
    new_name=len(names);names.extend(b'.m0_qfplib\0')
    strings=bytearray(original.bytes_at(sections[strings_index]))
    symbols=bytearray(original.bytes_at(sections[symbols_index]));seen=0
    assert sections[symbols_index][9]==sym.size
    for offset in range(0,len(symbols),sym.size):
        row=list(sym.unpack_from(symbols,offset))
        if original.string(strings,row[0])=='__flash_binary_end':
            row[1]=BASE+len(image);sym.pack_into(symbols,offset,*row);seen+=1
    assert seen==1
    for name,(address,size,kind) in sorted(exported.items()):
        name_offset=len(strings);strings.extend(name.encode('ascii')+b'\0')
        symbols.extend(sym.pack(name_offset,address,size,0x10|kind,0,new_index))
    raw=bytearray(original.data)
    for name in ['.text','.mk61_fw_footer']:
        s=original.named_sections[name];start=s[3]-BASE
        if name=='.mk61_fw_footer':assert start==footer_offset and s[5]==FOOTER.size
        raw[s[4]:s[4]+s[5]]=image[start:start+s[5]]
    def append(data,alignment=4):
        raw.extend(bytes((-len(raw))%alignment));offset=len(raw);raw.extend(data);return offset
    reference_offset=append(blob,4096)
    sections[strings_index][4]=append(strings);sections[strings_index][5]=len(strings)
    sections[symbols_index][4]=append(symbols);sections[symbols_index][5]=len(symbols)
    sections[names_index][4]=append(names);sections[names_index][5]=len(names)
    sections.append([new_name,1,6,REFERENCE_BASE,reference_offset,len(blob),0,0,8,0])
    segments=list(original.segments);assert all(s[0]!=6 for s in segments),'Unexpected PT_PHDR'
    reference_segment=(1,reference_offset,REFERENCE_BASE,REFERENCE_BASE,len(blob),len(blob),5,4096)
    position=next((i for i,s in enumerate(segments) if s[0]==1 and s[2]>REFERENCE_BASE),len(segments))
    segments.insert(position,reference_segment)
    h[5]=append(b''.join(ph.pack(*s) for s in segments));h[10]=len(segments)
    h[6]=append(b''.join(sh.pack(*s) for s in sections));h[12]=len(sections)
    header.pack_into(raw,0,*h)
    return bytes(raw)


def join_reference(out,production,qfp,adapters,composition=None,*,extra_flags=(),production_symbols=True):
    out,production=Path(out),Path(production)
    work=out/'reference-link';work.mkdir(exist_ok=True)
    firmware=out/'firmware';firmware.mkdir(exist_ok=True)
    tc=compiler_bin(None)
    flags=['-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-fno-lto',
           '-fno-unwind-tables','-fno-asynchronous-unwind-tables','-ffunction-sections','-fdata-sections',*extra_flags]
    objects=[]
    for source in [qfp,adapters]+([composition] if composition else []):
        source=Path(source);obj=work/(source.name+'.o')
        subprocess.run([str(tc/'arm-none-eabi-gcc'),*flags,'-c',str(source),'-o',str(obj)],check=True)
        objects.append(obj)
    linker=work/'reference.ld'
    linker.write_text('ENTRY(qfp_dadd)\nSECTIONS {\n'+
        f' .m0_qfplib 0x{REFERENCE_BASE:x} : {{ KEEP(*(.m0_qfplib)) *(.text*) *(.rodata*) }}\n'+
        ' .reference_ram (NOLOAD) : { *(.data*) *(.bss*) *(COMMON) }\n'+
        ' /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) }\n'+
        ' ASSERT(SIZEOF(.reference_ram)==0,"Reference must not add RAM state")\n}\n')
    reference=work/'reference.elf'
    resident_symbols=['-Wl,--just-symbols='+str(production.resolve())] if production_symbols else []
    subprocess.run([str(tc/'arm-none-eabi-gcc'),*flags,'-nostdlib',
        *resident_symbols,'-Wl,--no-undefined',
        '-Wl,-T,'+str(linker),'-Wl,-Map='+str(work/'reference.map'),
        *map(str,objects),'-o',str(reference)],check=True)
    ref=ElfImage(reference);section=ref.named_sections['.m0_qfplib']
    assert section[3]==REFERENCE_BASE and section[3]+section[5]<=0x101FE000
    blob=ref.bytes_at(section);blob_path=work/'reference.bin';blob_path.write_bytes(blob)
    manifest=json.loads((production.parent/'manifest.json').read_text())
    original=(production.parent/(TARGET+'.bin')).read_bytes()
    assert hashlib.sha256(original).hexdigest()==manifest['bin_sha256']
    original_elf=ElfImage(production)
    offset=manifest['firmware_integrity']['footer_offset'];verify(original,offset)
    assert len(original)<=REFERENCE_BASE-BASE
    image=bytearray(original+bytes(REFERENCE_BASE-BASE-len(original))+blob)
    assert original_elf.symbols['__flash_binary_end']==BASE+len(original)
    patches=[]
    # These callers encode the link-time extent in their literal pools. A
    # symbol-table edit alone cannot update the executable boot/recheck bounds.
    for name,old_value,new_value in [
        ('_ZN8picocalc8firmware7enforceEv',BASE+len(original),BASE+len(image)),
        ('_ZN8picocalc8firmware6reportEPcjb',len(original),len(image)),
    ]:
        start=(original_elf.symbols[name]&~1)-BASE
        end=start+original_elf.sizes[name]
        word=struct.pack('<I',old_value)
        positions=[i for i in range(start,end-3) if i%4==0 and original[i:i+4]==word]
        assert len(positions)==1,('Unrecognized firmware extent literal',name,positions)
        position=positions[0];struct.pack_into('<I',image,position,new_value)
        patches.append(dict(symbol=name,offset=position,size=4,before=hex(old_value),after=hex(new_value),
                            reason='Diagnostic image extent; no mathematical code changed'))
    struct.pack_into('<3I',image,offset+16,0,0,0)
    image=seal(bytes(image),offset)
    footer=work/'footer.bin';footer.write_bytes(image[offset:offset+FOOTER.size])
    types=symbol_types(ref)
    # Export reference entry points, retaining their Thumb values and sizes.
    exported={n:(a,ref.sizes[n],types[n]) for n,a in ref.symbols.items()
              if (types[n]==2 or n.startswith('qfp_')) and REFERENCE_BASE<=a<REFERENCE_BASE+len(blob)}
    assert exported and all(n not in original_elf.symbols for n in exported)
    elf_path=firmware/(TARGET+'.elf')
    elf_path.write_bytes(append_reference_elf(original_elf,blob,exported,image,offset))
    joined=ElfImage(elf_path)
    assert all(segment in joined.segments for segment in original_elf.segments),'Production program headers changed'
    assert joined.symbols['__flash_binary_end']==BASE+len(image)
    for name,(address,size,kind) in exported.items():
        assert (joined.symbols[name],joined.sizes[name])==(address,size)
        assert symbol_types(joined)[name]==kind
    ram_sections=0
    for name,before in original_elf.named_sections.items():
        if not before[2]&2 or not 0x20000000<=before[3]<0x20042000:continue
        after=joined.named_sections[name]
        assert (before[1:4],before[5])==(after[1:4],after[5]),('RAM layout changed',name)
        if before[1]!=8:assert original_elf.bytes_at(before)==joined.bytes_at(after),('RAM bytes changed',name)
        ram_sections+=1
    bin_path=firmware/(TARGET+'.bin')
    subprocess.run([str(tc/'arm-none-eabi-objcopy'),'-O','binary',str(elf_path),str(bin_path)],check=True)
    assert bin_path.read_bytes()==image,'Joined ELF changed production flash bytes or initializer'
    # Enforce byte identity outside the complete, explicit patch allowlist.
    preserved=bytearray(image[:len(original)])
    for patch in patches+[dict(offset=offset,size=FOOTER.size)]:
        at,size=patch['offset'],patch['size'];preserved[at:at+size]=original[at:at+size]
    assert bytes(preserved)==original,'Unlisted production flash modification'
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ports/picocalc'))
    from uf2 import encode,validate
    transport=encode(image);validate(transport,image)
    (firmware/(TARGET+'.uf2')).write_bytes(transport)
    proof=dict(status='PASS',mode='independent_reference_joined_after_production_link',
        production_elf_sha256=sha(production),reference_elf_sha256=sha(reference),
        reference_flash_address=REFERENCE_BASE,reference_bytes=len(blob),reference_sha256=sha(blob_path),
        original_flash_bytes=len(original),preserved_production_flash_bytes=len(original)-FOOTER.size-8,
        production_patches=patches+[dict(offset=offset,size=FOOTER.size,reason='Integrity footer covers the diagnostic reference')],
        ram_initializers_preserved=True,production_program_headers_preserved=True,preserved_ram_sections=ram_sections,
        reference_ram_bytes=0,reference_entry_points=len(exported))
    manifest.update(flash_bytes=len(image),uf2_bytes=len(transport),bin_sha256=hashlib.sha256(image).hexdigest(),
        uf2_sha256=hashlib.sha256(transport).hexdigest(),hardware_verified=False,
        firmware_integrity=verify(image,offset),diagnostic_reference=proof,
        source_identity_scope='Original production source/build ID retained; diagnostic reference is separately identified')
    (firmware/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (out/'reference-link-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof
