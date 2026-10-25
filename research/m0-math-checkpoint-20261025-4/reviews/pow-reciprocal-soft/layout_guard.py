"""Saved ELF-only layout/overlay checks, without mapping any physical device."""
import hashlib,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
e=ElfImage(O/'rebuild/candidate.elf');s=e.named_sections['.ddiv'];paths=[R/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf']
paths +=[R/'.build'/n/'candidate.elf'for n in ['m0-exp-cached-product-20261024','m0-pow-square-ordinary-20261024','m0-pow-rsqrt-asm-20261024','m0-pow-exp-table-product-20261025','m0-pow-square128-r2-20261025','m0-pow-boundary128-20261025']]
assert s[3]==0x101e1000 and s[5]==1050 and s[3]+s[5]<0x10200000
for p in paths:
 im=ElfImage(p)
 assert not any(t[2]&2 and t[5]and max(s[3],t[3])<min(s[3]+s[5],t[3]+t[5])for t in im.sections),p
assert not any(t[2]&2 and t[2]&1 and t[5]for t in e.sections)
# The inherited table entry hazard is still real after this new caller delta.
table=ElfImage(R/'.build/m0-pow-exp-table-product-20261025/candidate.elf');entry=table.symbols['mk61_m0_pow_exp_table_product']&~1
old=ElfImage(R/'.build/m0-exp-directed-product-20261024/candidate.elf');os=old.named_sections['.product_ram']
assert min(os[3]+os[5],entry+20)-max(os[3],entry)==14
out=dict(status='PASS_PRIVATE_DDIV_FREE_FLASH_NO_NEW_RAM_AND_PERSISTING_OVERLAY_HAZARD',
 current_diagnostic_allocation=dict(start=hex(s[3]),bytes=s[5],end=hex(s[3]+s[5])),no_overlap_checked_against=[ref(p)for p in paths],
 no_new_writable_allocations=True,current_private_ELF_not_combined_firmware=True,
 old168overlay_overlaps_new_table_entry14bytes=True,accepted_loader_orders_old_general_before_new_whole_table_bank=True,
 actual_own_CPU_table_entry_guards_passed=ref(O/'public-arm-mpfr.json'),
 actual_integrated_R12_and_loader_layout_guard_still_required=True,near_one_sibling_not_loaded=True,ARM_calls=0,MPFR_inputs=0,device_IO=0)
with (O/'layout.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(ref(O/'layout.json')),flush=True)
