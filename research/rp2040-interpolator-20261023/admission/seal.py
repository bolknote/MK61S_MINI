#!/usr/bin/env python3
"""Seal only the separate quiet-domain draft/model evidence; never open devices."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--guard-tests',type=Path,required=True)
    p.add_argument('--carrier-tests',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();assert not out.exists(),'Use a new sealed draft directory'
    guards=load(a.guard_tests/'report.json');carrier=load(a.carrier_tests/'report.json');plan=load(HERE/'integration-plan.json')
    assert guards['status']=='PASS_SYNTHETIC_GUARD_MODEL_ONLY' and len(guards['negative_cases'])==20
    assert carrier['status']=='PASS_DRAFT_SCOPED_CARRIER_MODEL_ONLY' and len(carrier['cases'])==7
    assert not guards['hardware_GO'] and not carrier['hardware_GO'] and not carrier['real_preservation_PASS']
    for report in (guards,carrier):
        for n,digest in report['source_sha256'].items():assert sha(HERE/n)==digest,n
    for n,digest in guards['fixture_sha256'].items():assert sha(a.guard_tests/n)==digest,n
    for name,reference in plan['source_references'].items():
        assert sha(reference['path'])==reference['sha256'],'Upstream reference changed; refresh explicit draft and targeted evidence: '+name
    assert load(HERE/'policy.UNBOUND.json')['accepted_base'] is None
    assert len(plan['current_provider_bindings'])==5 and not any(plan['current_provider_bindings'].values())
    out.mkdir(parents=True)
    def copy(original,relative):
        dest=out/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,dest)
    for n in ('quiet_guards.py','scoped.py','test_quiet_guards.py','test_scoped.py','seal.py','policy.UNBOUND.json','integration-plan.json','README.md'):
        copy(HERE/n,'source/'+n)
    for name,reference in plan['source_references'].items():copy(reference['path'],'references/'+name+Path(reference['path']).suffix)
    for n in ('report.json','FIXTURE-policy.json','FIXTURE-data.json'):copy(a.guard_tests/n,'evidence/guards/'+n)
    copy(a.carrier_tests/'report.json','evidence/carrier/report.json')
    for row in carrier['cases']:copy(a.carrier_tests/row['case']/'receipt.json','evidence/carrier/'+row['case']+'/receipt.json')
    summary=dict(status='SEALED_SCOPED_COMPARE_DRAFT_FOR_REVIEW',hardware_GO=False,real_preservation_PASS=False,
        combined_manifest_sha256=plan['combined_manifest_sha256'],guard_negative_cases=20,guard_positive_cases=2,carrier_cases=7,
        providers=plan['current_provider_bindings'],accepted_repaired_base=None,
        scope='Separate narrow-domain orchestration and synthetic normalized guards. No raw observer/authority verifier/real SD or UI-return provider/port factory exists.',
        next='Independent focused draft review, then implement/review real interfaces against the accepted repaired base and obtain a fresh scoped lease.')
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    files={str(f.relative_to(out)):dict(bytes=f.stat().st_size,sha256=sha(f))for f in sorted(out.rglob('*'))if f.is_file()}
    manifest=out/'draft-manifest.json';manifest.write_text(json.dumps(dict(schema=1,status=summary['status'],hardware_GO=False,files=files),indent=2)+'\n')
    handoff=dict(status=summary['status'],manifest=str(manifest),manifest_sha256=sha(manifest),files=len(files),hardware_GO=False,
                 provider_plan=str(out/'source/integration-plan.json'),next=summary['next'])
    (HERE.parent/'QUIET-ADMISSION-HANDOFF.json').write_text(json.dumps(handoff,indent=2)+'\n');print(json.dumps(handoff,indent=2))


if __name__=='__main__':main()
