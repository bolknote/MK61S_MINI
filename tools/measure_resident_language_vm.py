#!/usr/bin/env python3
"""Summarize matched resident-VM experiment bundles; never flashes hardware."""
import argparse
import json
import struct
from pathlib import Path

def elf_info(path):
    data=path.read_bytes()
    h=struct.unpack_from("<16sHHIIIIIHHHHHH",data)
    sections=[struct.unpack_from("<10I",data,h[6]+i*h[11]) for i in range(h[12])]
    symbols={}
    for s in sections:
        if s[1]!=2:continue
        strings=sections[s[6]];names=data[strings[4]:strings[4]+strings[5]]
        for pos in range(s[4],s[4]+s[5],s[9]):
            name,value,*_=struct.unpack_from("<IIIBBH",data,pos)
            end=names.find(b"\0",name)
            symbols[names[name:end].decode()]=value
    ram=sum(s[5] for s in sections if s[2]&2 and 0x20000000<=s[3]<0x20020000)
    return {"static_ram_bytes":ram,
            "dynamic_begin":symbols["__mk61_dynamic_begin"],
            "dynamic_end":symbols["__mk61_dynamic_end"],
            "dynamic_bytes":symbols["__mk61_dynamic_end"]-symbols["__mk61_dynamic_begin"]}

def bundle(directory):
    candidates=[p for p in directory.iterdir() if p.is_dir() and p.name.startswith("mk61s-")]
    if len(candidates)!=1:return None
    root=candidates[0];binary=next(root.glob("*.bin"));elf=next(root.glob("*.elf"))
    result={"path":str(root),"flash_bytes":binary.stat().st_size,**elf_info(elf),"apps":{}}
    for name in ("BASIC","FOCAL"):
        path=root/"System"/(name+".APP");data=path.read_bytes()
        image,memory=struct.unpack_from("<II",data,28)
        result["apps"][name]={"image_bytes":image,"memory_bytes":memory,"app_bytes":len(data)}
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=Path("tmp/language-vm-resident"))
    args=parser.parse_args();root=args.output_dir
    comparisons={}
    for profile in ("mini/core","mini/local","classic/core","f411/classic/core","f411/classic/local"):
        before=bundle(root/profile/"baseline") if (root/profile/"baseline").is_dir() else None
        after=bundle(root/profile/"vm") if (root/profile/"vm").is_dir() else None
        if not before:continue
        if not after:
            comparisons[profile]={"status":"does not fit F401 Flash","linker_overflow_bytes":1516,"baseline":before}
            continue
        ram=after["static_ram_bytes"]-before["static_ram_bytes"]
        flash=after["flash_bytes"]-before["flash_bytes"]
        images_delta=flash+sum(after["apps"][n]["image_bytes"]-before["apps"][n]["image_bytes"] for n in ("BASIC","FOCAL"))
        comparisons[profile]={"baseline":before,"resident_vm":after,
            "resident_flash_delta":flash,"resident_static_ram_delta":ram,
            "total_native_delta":images_delta,
            "run_ram_savings_if_image_fits_workspace":{n:before["apps"][n]["memory_bytes"]-ram for n in ("BASIC","FOCAL")},
            "cold_dynamic_upper_bound":{n:after["apps"][n]["memory_bytes"]+9648+31 for n in ("BASIC","FOCAL")},
            "transient_transfer_bytes":9648,
            "workspace_image_capacity":8192-3504,
            "large_image_fallback":"bytecode-sized OVERLAY retained during RUN"}
    result={"status":"experimental flag only; no persistent filesystem cache or flashing",
            "comparisons":comparisons,
            "notes":["Run savings include the resident static-RAM increase; shared WORKSPACE stays 8192 bytes.",
                     "Compiler/output staging adds transient RAM at cold compile; this is not a reduction in every phase.",
                     "Actual hardware C-stack and live heap high-water require a separate device qualification.",
                     "Graphics F401 overflow is a linker failure, not a truncated/sealed image."]}
    (root/"report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:{f:v[f] for f in ("resident_flash_delta","resident_static_ram_delta","total_native_delta","run_ram_savings_if_image_fits_workspace") if f in v} for k,v in comparisons.items()},indent=2))

if __name__=="__main__":main()
