#!/usr/bin/env python3
"""Freeze matched private ZX0 variants; never edit production codec sources."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def replace_once(text, before, after):
    assert text.count(before) == 1, (before, text.count(before))
    return text.replace(before, after)


BASELINE_REF = '6781f4a248ecfcc683f70a75269cbb21052f34d7'


def prepare(out):
    out.mkdir(parents=True, exist_ok=True)
    originals = {name: subprocess.check_output(['git','show',BASELINE_REF+':code/'+name],cwd=ROOT,text=True) for name in ('zx0.hpp', 'zx0.cpp', 'zx0_encode.cpp')}
    assert 'static constexpr u16 MAX_OFFSET = 256;' in originals['zx0_encode.cpp']
    assert 'static constexpr u32 MAX_INPUT_SIZE = 8192;' in originals['zx0_encode.cpp']
    files = []
    for variant in ('scalar', 'word', 'dsp'):
        ns = 'zx0_private_' + variant
        header = originals['zx0.hpp'].replace('MK61_ZX0_HPP', 'MK61_ZX0_PRIVATE_' + variant.upper() + '_HPP')
        header = header.replace('namespace zx0 {', 'namespace ' + ns + ' {')
        (out/(variant+'.hpp')).write_text(header)
        decoder = originals['zx0.cpp']
        encoder = originals['zx0_encode.cpp']
        if variant != 'scalar':
            start = decoder.index('  if(offset > (u32) (output - begin)')
            end = decoder.index('\n}', start)
            decoder = decoder[:start] + '  return zx0_candidates::copy_word(output, begin, end, offset, length);' + decoder[end:]
            start = encoder.index('  const u8* current = input + position;')
            end = encoder.index('\n}', start)
            encoder = encoder[:start] + '  return zx0_candidates::match_word(input, size, position, offset);' + encoder[end:]
            encoder = replace_once(encoder,
                '    const u16 maximum_offset =\n      position < MAX_OFFSET ? position : MAX_OFFSET;\n    u16 near_length = 0;',
                '    u16 near_length = 0;')
            start = encoder.index('    for(u16 offset = 1; offset <= MAX_OFFSET; offset++) {')
            end = encoder.index('\n\n    u16 best_match', start)
            encoder = encoder[:start] + '    zx0_candidates::lcp_blocks<' + ('true' if variant == 'dsp' else 'false') + \
                '>(input, position, lcp, near_length, far_length);' + encoder[end:]
        sources = []
        for text in (decoder, encoder):
            text = text.replace('#include "zx0.hpp"', '#include "'+variant+'.hpp"')
            text = text.replace('namespace zx0 {', 'namespace '+ns+' {')
            sources.append(text)
        prefix = '#if defined(__GNUC__) && !defined(__clang__)\n#pragma GCC optimize ("Os")\n#endif\n'
        prefix += '#include "zx0_candidates.hpp"\n#include "zx0_prototypes.hpp"\n'
        wrappers = f'''
#if defined(__GNUC__) && !defined(__clang__)
#define WRAPPER __attribute__((noipa, aligned(16)))
#else
#define WRAPPER __attribute__((noinline, aligned(16)))
#endif
namespace zx0_prototypes {{
WRAPPER bool decode_{variant}(const zx0::Input& in,u32 n,u8* out,u32 capacity,u32& written) {{
  const {ns}::Input source={{in.context,in.next}};
  return {ns}::decode(source,n,out,capacity,written);
}}
WRAPPER bool encode_{variant}(const u8* in,u32 n,u8* work,usize bytes,
                              const zx0::Output& out,zx0::EncodeResult& result) {{
  const {ns}::Output sink={{out.context,out.next}};
  {ns}::EncodeResult value={{}};
  const bool ok={ns}::encode(in,n,work,bytes,sink,value);
  result.output_size=value.output_size;
  result.mode=(zx0::EncodeMode)value.mode;
  return ok;
}}
}}
#undef WRAPPER
'''
        path = out/(variant+'.cpp')
        path.write_text(prefix + '\n'.join(sources) + wrappers)
        files.append(str(path))
    manifest = {'source_commit': BASELINE_REF,
        'production_sha256': {name: hashlib.sha256(text.encode()).hexdigest() for name,text in originals.items()},
        'generated_sources': files,
        'scope': 'Private source-matched scalar/word/DSP codec variants, not installed firmware. '
                 'DSP differs from word only in the bounded encoder LCP table update; both decoders use the same word copy.'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output_dir.resolve()),indent=2))
