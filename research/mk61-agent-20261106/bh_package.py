"""Keep the wire codec; publish stricter checker and explicit natural-data provenance."""
import argparse
from pathlib import Path
import shutil
from bh_common import ROOT,HERE,SOURCES,read,write,sha

def main(root):
    assert read(root/'native-verification.json')['complete']
    for role in ['parent_lora','lora','parent_full','full']:
        branch=role.split('_',1)[-1];folder=root/'export'/role;before={n:sha(folder/n)for n in ['model.mkqb','model.mka']}
        schema=read(SOURCES[branch]/'wire-format.json');schema.update(experiment='spec-pairs-v1',role=role,
            generated_spec_is_not_confirmation_of_request=True,
            checker='relative2e-6 for nonzero; absolute1e-12 for zero; ROM sign(0)=0',
            default_exam_used_canonical_harness=False)
        write(folder/'wire-format.json',schema);runtime=folder/'protocol-source';runtime.mkdir(exist_ok=True)
        for n in ['ay_codec.py','ay_runtime.py','az_runtime.py','ay_chat.py','az_chat.py','az_teacher.py','ay_teacher.py',
                'ax_completion.py','ba_pools.py','bb_canonical.py','bb_session.py','bb_chat.py','bh_spec.py']:
            shutil.copyfile(HERE/n,runtime/n)
        write(folder/'protocol-source-sha256.json',{p.name:sha(p)for p in runtime.iterdir()if p.is_file()})
        m=read(folder/'manifest.json');m.update(experiment='spec-pairs-v1',role=role,parent_packet_sha256=sha(SOURCES[branch]/'model.mkqb'),
            dictionary_token_ids_unchanged=True,selection_used_closed_test=False)
        write(folder/'manifest.json',m);assert before=={n:sha(folder/n)for n in before}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT/'server-results');a=p.parse_args();main(a.root)
