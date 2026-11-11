"""Attach the unchanged SPEC protocol and explicit research-profile provenance."""
import argparse
from pathlib import Path
import shutil
from be_common import ROOT,HERE,SOURCE,read,write,sha

def main(root):
    assert read(root/'native-verification.json')['complete'];selection=read(root/'preselected.json')
    for role in ['parent','lora','full']:
        folder=root/'export'/role;before={n:sha(folder/n)for n in ['model.mkqb','model.mka']}
        schema=read(SOURCE/'wire-format.json');schema.update(experiment='spec-translation-clean-v1',role=role,
            generated_spec_is_not_confirmation_of_request=True,default_exam_used_canonical_harness=False,
            literal_pool_training='same default/extras/full/distractor views for both branches')
        write(folder/'wire-format.json',schema);runtime=folder/'protocol-source';runtime.mkdir(exist_ok=True)
        for n in ['ay_codec.py','ay_runtime.py','az_runtime.py','ay_chat.py','az_chat.py','az_teacher.py','ay_teacher.py',
                'ax_completion.py','ba_pools.py','bb_canonical.py','bb_session.py','bb_chat.py']:
            shutil.copyfile(HERE/n,runtime/n)
        write(folder/'protocol-source-sha256.json',{p.name:sha(p)for p in runtime.iterdir()if p.is_file()})
        m=read(folder/'manifest.json');m.update(experiment='spec-translation-clean-v1',role=role,
            parent_packet_sha256=sha(SOURCE/'model.mkqb'),selection_used_closed_test=False,
            Russian_dictionary_token_ids_unchanged=True,input_embedding_weights_frozen=role!='full')
        if role!='parent':m.update(selected_step=selection['branches'][role]['step'],
            selected_checkpoint_sha256=selection['branches'][role]['sha256'])
        write(folder/'manifest.json',m)
        assert before=={n:sha(folder/n)for n in before}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT/'server-results');a=p.parse_args();main(a.root)
