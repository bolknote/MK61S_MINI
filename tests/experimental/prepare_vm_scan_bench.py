#!/usr/bin/env python3
"""Harvest actual compiler scan calls into a compact ordinary-APP replay.

Only a private compiler copy is instrumented. Records are deduplicated with
their original call weights; the generated fixture uses the real M8 bytes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import m8_codec

SOURCES = (
    ('basic', 'programs/games/Turochamp/search.tbi'),
    ('basic', 'programs/games/High Noon/intro.tbi'),
    ('focal', 'tests/data/language_compression/statistics.foc'),
)

PROBE = r'''
#include <cstdio>
#include <cstdlib>
#include <map>
#include <string>
#include <tuple>
#include <vector>
#include "language_bytecode.hpp"
namespace vm_scan_trace {
using Key=std::tuple<unsigned,std::string,std::string>;
static std::map<Key,unsigned> records;
void scan(unsigned kind,const char* p,size_t n,const char* q,size_t qn) {
  ++records[{kind,std::string(p,n),q ? std::string(q,qn) : std::string()}];
}
}
static void hex(const std::string& s) {
  std::putchar('"');
  for(unsigned char c:s) std::printf("%02x",c);
  std::putchar('"');
}
int main(int argc,char** argv) {
  if(argc!=3) return 2;
  FILE* file=std::fopen(argv[2],"rb");
  if(!file) return 2;
  std::vector<uint8_t> source(3585),image(language_vm::MAX_MODULE);
  const size_t n=std::fread(source.data(),1,source.size(),file);
  std::fclose(file);
  if(n>=source.size()) return 2;
  const auto language=argv[1][0]=='b' ? language_vm::Language::BASIC : language_vm::Language::FOCAL;
  language_vm::ResourceSource resources={42,1};
  resources.mode=language_vm::ResourceMode::EMBEDDED;
  auto result=language_vm::compile(language,(const char*)source.data(),(uint16_t)n,
      nullptr,language_vm::MAX_MODULE,true,&resources);
  if(result.error!=language_vm::Error::NONE) return 3;
  result=language_vm::compile(language,(const char*)source.data(),(uint16_t)n,
      image.data(),language_vm::MAX_MODULE,true,&resources);
  if(result.error!=language_vm::Error::NONE) return 4;
  std::printf("{\"bytecode_bytes\":%u,\"records\":[",result.size);
  bool comma=false;
  for(const auto& row:vm_scan_trace::records) {
    if(comma) std::putchar(',');comma=true;
    std::printf("[%u,",std::get<0>(row.first));
    hex(std::get<1>(row.first));std::putchar(',');hex(std::get<2>(row.first));
    std::printf(",%u]",row.second);
  }
  std::puts("]}");
}
'''


def replace_once(text, old, new):
    assert text.count(old) == 1, f'compiler anchor changed: {old!r}'
    return text.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    original = (ROOT / 'code/language_bytecode.cpp').read_text()
    text = original
    text = replace_once(text, 'namespace language_vm {',
        'namespace vm_scan_trace { void scan(unsigned,const char*,size_t,const char*,size_t); }\nnamespace language_vm {')
    text = replace_once(text, '      const char* begin = cursor;',
        '      const char* begin = cursor;\n      vm_scan_trace::scan(0,cursor,(size_t)(source_+length_-cursor),nullptr,0);')
    text = replace_once(text, '  void skip() {',
        '  void skip() {\n    vm_scan_trace::scan(1,p_,(size_t)(end_-p_),nullptr,0);')
    text = replace_once(text, '    const char* saved = p_;\n    uint8_t n = 0;',
        '    const char* saved = p_;\n    vm_scan_trace::scan(2,p_,(size_t)(end_-p_),word,minimum);\n    uint8_t n = 0;')
    text = replace_once(text, '        bool same=n==length;',
        '        char traced[3584];\n        if(n>sizeof(traced)) {fail(Error::FULL);return 0;}\n'
        '        for(uint16_t i=0;i<n;++i) traced[i]=(char)*resource_data_.at((uint16_t)(at+2+i));\n'
        '        vm_scan_trace::scan(3,traced,n,text,length);\n        bool same=n==length;')
    # Capture full keyword text + minimum in the right-hand payload.
    probe = PROBE.replace('++records[{kind,std::string(p,n),q ? std::string(q,qn) : std::string()}];',
        'std::string right;\n'
        '  if(kind==2) {right=std::string(1,(char)qn);right+=q;}\n'
        '  else if(q) right.assign(q,qn);\n'
        '  ++records[{kind,std::string(p,n),right}];')
    (out / 'traced_compiler.cpp').write_text(text)
    (out / 'trace_probe.cpp').write_text(probe)
    subprocess.run([shutil.which('clang++') or 'c++','-std=c++17','-O1',
        '-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-fno-omit-frame-pointer','-I'+str(ROOT/'code'),out/'trace_probe.cpp',
        out/'traced_compiler.cpp','-o',out/'trace_probe'],check=True)
    blob = bytearray()
    interned = {}

    def intern(data):
        if data not in interned:
            # Reuse substrings, especially the many suffixes of one source.
            found = blob.find(data)
            if found < 0:
                found = len(blob)
                blob.extend(data)
            interned[data] = found
        return interned[data]

    cases = []
    records = []
    for language, name in SOURCES:
        payload = m8_codec.encode((ROOT/name).read_text(encoding='utf-8-sig'))
        path = out / (Path(name).stem+'.m8')
        path.write_bytes(payload)
        intern(payload)
        trace = json.loads(subprocess.check_output([out/'trace_probe',language,path],text=True))
        (out/(Path(name).stem+'-calls.json')).write_text(json.dumps(trace)+'\n')
        groups = []
        for kind in range(4):
            original_rows = [row for row in trace['records'] if row[0] == kind]
            # Coalesce calls with the same branch shape, retaining their exact
            # weights. This fits real-program replay in the ordinary APP arena.
            # Line scanning keeps every original line; short token predicates
            # depend on prefix, bounds and first mismatch rather than suffix.
            strata = {}
            for row in original_rows:
                left, right = bytes.fromhex(row[1]), bytes.fromhex(row[2])
                if kind == 0:
                    key = left
                elif kind == 1:
                    prefix = next((i for i,c in enumerate(left) if c not in (9,32)),len(left))
                    key = (prefix,min(len(left),4))
                elif kind == 2:
                    minimum, word = right[0],right[1:]
                    prefix = next((i for i,c in enumerate(left) if not 65 <= (c & ~32) <= 90),len(left))
                    dotted = prefix < len(left) and left[prefix] == 46
                    eligible = prefix != 0 and (minimum <= prefix <= len(word) if dotted else prefix == len(word))
                    mismatch = next((i for i in range(prefix) if (left[i]-32 if 97 <= left[i] <= 122 else left[i]) != word[i]),prefix) if eligible else -1
                    key = (prefix,dotted,minimum,len(word),mismatch,min(len(left),4))
                else:
                    mismatch = next((i for i,(a,b) in enumerate(zip(left,right)) if a != b),len(left)) if len(left) == len(right) else -1
                    key = (False,) if len(left) != len(right) else (True,len(left),mismatch)
                if key in strata:
                    strata[key][3] += row[3]
                else:
                    strata[key] = list(row)
            rows = list(strata.values())
            start = len(records)
            histogram = {}
            calls = 0
            for _, left_hex, right_hex, weight in rows:
                left, right = bytes.fromhex(left_hex), bytes.fromhex(right_hex)
                if kind == 2:
                    minimum, right = right[0], right[1:]
                else:
                    minimum = 0
                assert len(left) < 65536 and len(right) < 65536 and weight < 65536
                records.append((intern(left),len(left),intern(right),len(right),weight,minimum,0))
                # Histogram of the actual scalar prefix/mismatch, not the
                # remaining source length in a pointer/end call.
                if kind == 0:
                    useful = next((i for i,c in enumerate(left) if c in (10,13)),len(left))
                elif kind == 1:
                    useful = next((i for i,c in enumerate(left) if c not in (9,32)),len(left))
                elif kind == 2:
                    useful = next((i for i,c in enumerate(left) if not 65 <= (c & ~32) <= 90),len(left))
                elif len(left) != len(right):
                    useful = 0
                else:
                    useful = next((i for i,(a,b) in enumerate(zip(left,right)) if a != b),len(left))
                histogram[useful] = histogram.get(useful,0)+weight
                calls += weight
            groups.append({'start':start,'count':len(rows),'original_unique_calls':len(original_rows),'calls':calls,
                           'useful_prefix_histogram':histogram})
        cases.append({'language':language,'source':name,'source_bytes':len(payload),
            'source_sha256':hashlib.sha256(payload).hexdigest(),
            'bytecode_bytes':trace['bytecode_bytes'],'groups':groups})
    assert len(blob)<65536 and len(records)<65536
    lines = ['// Generated from private host compiler trace; no product hooks.',
        'struct ScanRecord { uint16_t left,length,right,right_length,weight; uint8_t minimum,reserved; };',
        'struct ScanGroup { uint16_t start,count; uint32_t calls; };',
        'static const uint8_t fixture_blob[] = {']
    for at in range(0,len(blob),24):
        lines.append('  '+','.join(str(x) for x in blob[at:at+24])+',')
    lines += ['};','static const ScanRecord fixture_records[] = {']
    lines += ['  {'+','.join(str(x) for x in row)+'},' for row in records]
    lines += ['};','static const ScanGroup fixture_groups[][4] = {']
    for case in cases:
        lines.append('  {'+','.join('{'+','.join(str(group[k]) for k in ('start','count','calls'))+'}'
                                   for group in case['groups'])+'},')
    lines += ['};',f'static constexpr unsigned fixture_case_count={len(cases)};']
    (out/'vm_scan_fixture.hpp').write_text('\n'.join(lines)+'\n')
    (out/'fixture.json').write_text(json.dumps({'compiler_sha256':hashlib.sha256(original.encode()).hexdigest(),
        'blob_bytes':len(blob),'records':len(records),'cases':cases,
        'scope':'actual calls from sizing+EMIT with owned resources; branch-shape coalesced weighted kernel replay, not complete compilation'},indent=2)+'\n')
    print(f'VM scan fixture: {len(cases)} sources, {len(records)} records, {len(blob)} blob bytes')


if __name__ == '__main__':
    main()
