"""Check the two published packages, including permuted-table token streams."""
import argparse
from pathlib import Path
import ay_native as base
from az_native import choose as original_choose
from bc_common import SOURCE,sha,read,write


def choose(report):
    probes=original_choose(report);seen={p['prompt']for p in probes}
    for mode,value in report['pool_views'].items():
        candidates=[r for r in value['records']if not r['generation'].get('codec_error')]
        for r in candidates[:2]:
            if r['prompt']not in seen:
                probes.append({'prompt':r['prompt'],'generation':r['generation'],'forced_action':'write'});seen.add(r['prompt'])
    for panel in ['self','controlled_checks']:
        histories=[h for r in report[panel]['records']for h in r['history']if'prompt'in h and'fragment'not in h]
        for action in ['unsure','write','done']:
            values=[h for h in histories if h.get('generation',{}).get('action')==action and'DONE_REJECTED'in h['prompt']and not h['generation'].get('codec_error')]
            for h in values[:2]:
                if h['prompt']not in seen:probes.append({'prompt':h['prompt'],'generation':h['generation'],'forced_action':None});seen.add(h['prompt'])
    return probes


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--supplementary',action='store_true');a=p.parse_args();root=a.root.resolve()
    previous=read(root/'native-verification.json')if a.supplementary else None
    if previous is not None:
        assert set(previous['models'])=={'parent','spec'}
        write(root/'balanced-native-verification.json',previous)
    base.ARMS=['safety']if a.supplementary else['parent','spec'];base.choose=choose;base.main(root)
    assert sha(root/'export/parent/model.mka')==sha(SOURCE/'model.mka'),'Baseline native package changed'
    receipt=read(root/'native-verification.json');receipt.update(selector_source_sha256=sha(Path(__file__)),parent_MKA_identical=True)
    if previous is not None:
        write(root/'supplementary-native-verification.json',receipt)
        receipt['models']={**previous['models'],**receipt['models']}
        receipt['balanced_receipt_sha256']=sha(root/'balanced-native-verification.json')
        receipt['supplementary_receipt_sha256']=sha(root/'supplementary-native-verification.json')
    write(root/'native-verification.json',receipt)
