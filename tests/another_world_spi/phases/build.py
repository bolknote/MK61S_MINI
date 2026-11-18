"""Build the frame-2440 probe and replay both measurement modes on the host."""
import argparse
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SPI = HERE.parent
ROOT = SPI.parent.parent
sys.path.insert(0, str(ROOT))
from tools.apps.another.build_another_app import SOURCES
from tools.firmware.picocalc.build_picocalc import compiler_bin

GAME = ROOT / "examples/portable-apps/ANOTHER"


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError("source landmark changed: " + old)
    return source.replace(old, new)


def sources(out):
    # Instrument copies so the ordinary game and its A/B reference stay intact.
    storm = '#include "hooks.h"\n' + (GAME/"display_storm.cpp").read_text()
    old = "    return store(*slot.assets, r.offset, slot.scratch, unsigned(r.width) * r.height, false);"
    storm = once(storm, old, """    const unsigned saved=ph_prepare(r.x*2u,r.y,r.width*2u,r.height,0);
    const bool ok=store(*slot.assets,r.offset,slot.scratch,unsigned(r.width)*r.height,false);
    ph_leave(saved);
    return ok;""")
    old = "    memset(slot.scratch, tail.black_pair, rows * AW_VIDEO_STRIDE);"
    storm = once(storm, old, """    const unsigned saved=ph_prepare(0,y,AW_VIDEO_WIDTH,rows,1);
""" + old + "\n    ph_leave(saved);")
    start = storm.index("bool draw_tail_frame(")
    old = "    if (memcmp(palette, s.palette[frame.page], AW_STORM_PALETTE_BYTES) ||\n        aw_storm_frame_hash(pixels, palette) != frame.hash) return false;"
    storm = storm[:start] + once(storm[start:], old, """    const unsigned saved=ph_enter(PH_HASH);
    const bool matches=!memcmp(palette,s.palette[frame.page],AW_STORM_PALETTE_BYTES) &&
        aw_storm_frame_hash(pixels,palette)==frame.hash;
    ph_leave(saved);
    if(!matches) return false;""")
    (out/"display_storm.cpp").write_text(storm)
    # The measured calls can contain early returns; wrap the function itself.
    units = {
        "video.c": [("aw_video_polygon","PH_POLYGON","v,base,size,offset,zoom,x,y"),
                    ("aw_video_copy","PH_COPY","v,src,dst,scroll"),("aw_video_fill","PH_FILL","v,page,color")],
        "audio.c": [("aw_audio_render","PH_AUDIO","a,out,count")],
    }
    for name, wrappers in units.items():
        text = '#include "hooks.h"\n' + (GAME/name).read_text()
        for fn, bucket, params in wrappers:
            offset = text.index("bool " + fn + "(")
            signature = text[offset:text.index("{",offset)].strip()
            text = once(text,signature+" {","static "+signature.replace(fn,fn+"_measured",1)+" {")
            text += "\n"+signature+" {\n" + f"    unsigned saved=ph_enter({bucket});\n    bool ok={fn}_measured({params});\n    ph_leave(saved);\n    return ok;\n}}\n"
        (out/name).write_text(text)
    return [SPI/"main.c" if name=="main.c" else (out/name if name in (*units,"display_storm.cpp") else GAME/name)
            for name in SOURCES]


def host_mock():
    mock = (ROOT/"tests/another_world_app_host_test.c").read_text()
    mock = once(mock,'#include "../examples/portable-apps/ANOTHER/video.h"','#include "video.h"')
    return once(mock,"static uint32_t sizes[5];","static uint32_t sizes[5];\nuint32_t aw_phase_mock_us(void) { return now_ms*1000u; }")


def compile_host(out, units, main_source, mock, defines=("AW_CS_PHASE",)):
    common = ["-O2","-g","-Wall","-Wextra","-Werror",*["-D"+name for name in defines],"-DAW_TRACE_HOST",
              "-fsanitize=address,undefined","-fno-sanitize-recover=all",
              "-I",GAME,"-I",SPI,"-I",HERE,"-I",ROOT/"sdk/portable/include","-I",ROOT/"code"]
    (out/"mock.c").write_text(mock)
    objects = []
    for cpp in [out/"display_storm.cpp", ROOT/"code/zx0.cpp"]:
        obj = out/(cpp.stem+".host.o")
        subprocess.run(["c++","-std=c++17",*common,"-fno-exceptions","-c",cpp,"-o",obj],check=True)
        objects.append(obj)
    obj = out/"main.host.o"
    subprocess.run(["cc","-std=c11",*common,"-Dmain=another_app_main","-c",main_source,"-o",obj],check=True)
    app = out/"phase-host"
    subprocess.run(["cc","-std=c11",*common,"-DAW_TEST_LCD_READBACK",out/"mock.c",
                    *[p for p in units if p.name not in ("main.c","display_storm.cpp")],obj,*objects,"-o",app],check=True)
    return app


def host(out, units, data):
    app = compile_host(out, units, SPI/"main.c", host_mock())
    # The control marker belongs to a temporary fixture, never to the user's game.
    from tempfile import TemporaryDirectory
    from replay import parse
    with TemporaryDirectory(dir=out) as tmp:
        fixture=Path(tmp)
        for source in data.iterdir():
            if source.is_file() and source.name.casefold()!="awphctl.tag":
                (fixture/source.name).symlink_to(source)
        for mode in ("detail","control"):
            if mode=="control": (fixture/"AWPHCTL.TAG").write_bytes(b"2440")
            log = subprocess.check_output([app,fixture,"profile-pages"],text=True)
            (out/f"host-{mode}.txt").write_text(log)
            parse(log, mode, host=True)
            print(mode,"67 displayed frames matched the live VM; eight rectangle payloads verified",flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=ROOT/".build/another-cs2440")
    parser.add_argument("--pioasm",default="pioasm")
    parser.add_argument("--toolchain",type=Path)
    parser.add_argument("--check-data",type=Path)
    args=parser.parse_args()
    out=args.output_dir.resolve()
    out.mkdir(exist_ok=True,parents=True)
    units=sources(out)
    header=out/"wire.pio.h"
    subprocess.run([args.pioasm,"-v","0","-o","c-sdk",SPI/"wire.pio",header],check=True)
    subprocess.run([sys.executable,SPI/"test_pio.py",header],check=True)
    argv=[sys.executable,ROOT/"tools/apps/portable/build_portable_app.py","--target","picocalc-pico-h",
          "--shared-runtime","--name","AWPHASE","--arm-toolchain-bin",compiler_bin(args.toolchain),
          "--output-dir",out/"arm","--define","AW_CS_PHASE","--include",GAME,"--include",SPI,
          "--include",HERE,"--include",out]
    for source in (ROOT/"code/zx0.cpp",ROOT/"sdk/portable/rp2040_divide.S",*units):
        argv.extend(["--source",source])
    subprocess.run(argv,check=True)
    if args.check_data: host(out,units,args.check_data.resolve())


if __name__=="__main__":
    main()
