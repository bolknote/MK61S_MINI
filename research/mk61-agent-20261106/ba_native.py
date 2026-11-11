"""Check the two published packages, including permuted-table token streams."""
import argparse
from pathlib import Path
import ay_native as base
from az_native import choose as original_choose
from ba_common import SOURCE,sha,read,write


def choose(report):
    probes=original_choose(report);seen={p['prompt']for p in probes}
    for mode,value in report['pool_views'].items():
        candidates=[r for r in value['records']if not r['generation'].get('codec_error')]
        for r in candidates[:2]:
            if r['prompt']not in seen:
                probes.append({'prompt':r['prompt'],'generation':r['generation'],'forced_action':'write'});seen.add(r['prompt'])
    return probes


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve()
    base.ARMS=['parent','spec'];base.choose=choose;base.main(root)
    assert sha(root/'export/parent/model.mka')==sha(SOURCE/'model.mka'),'Baseline native package changed'
    receipt=read(root/'native-verification.json');receipt.update(selector_source_sha256=sha(Path(__file__)),parent_MKA_identical=True)
    write(root/'native-verification.json',receipt)
