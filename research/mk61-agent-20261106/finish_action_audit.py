"""Recover a completed audit whose final console-only summary formatting failed."""
import json
import time
from aa_common import ROOT,HERE,INITIAL,INITIAL_PACKET,read,write,sha
from run_experiment import run,SCRIPT


def main():
    selection=json.loads((ROOT/'preselected.json').read_text())
    for arm in ['sft','preference']:
        r=json.loads((ROOT/(arm+'-audit.json')).read_text())
        assert r['language']['total']==250 and r['tools']['total']==500
        assert r['isa']['total']==648 and r['legacy']['total']==98
        assert r['from_scratch']['total']==64 and r['fresh_used_for_selection']is False
        assert r['packed_sha256']==sha(ROOT/arm/'audit.mkqb')
        for stage in range(1,5):assert json.loads((ROOT/arm/f'training-stage-{stage}.json').read_text())['steps']==400
        assert selection['choices'][arm]['master_sha256']==sha(ROOT/arm/'best/model.safetensors')
    for name,digest in json.loads((ROOT/'prepared.json').read_text())['source_hashes'].items():assert sha(HERE/name)==digest,name
    write(ROOT/'audit-log-formatting-error.json',{'error':'brief() treated audit metadata bool as a dict after full results were written',
          'optimizer_rerun':False,'audit_rerun':False,'two_complete_audits_and_packet_hashes_verified':True,
          'selection_unchanged':True,'training_source_unchanged':True})
    write(ROOT/'status.json',{'phase':'exporting_recovered_audits','unix':time.time()})
    run('action-alignment-v1/export.log',SCRIPT+'aa_export.py',timeout=3600)
    data=json.loads((ROOT/'data-frozen.json').read_text())
    assert sha(INITIAL/'model.safetensors')==data['initial_master_sha256']and sha(INITIAL_PACKET)==data['initial_packet_sha256']
    write(ROOT/'complete.json',{'completed':True,'warmup_updates':600,'updates_each':1600,'source_unchanged':True,
                               'audit_console_error_recovered_without_rerunning_exams':True})
    write(ROOT/'status.json',{'phase':'complete','unix':time.time(),'audit_console_error_recovered':True})
    print('RECOVERED_COMPLETE',flush=True)


if __name__=='__main__':main()
