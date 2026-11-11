"""Keep the existing SPEC wire format; attach provenance and inference code."""
import argparse
from pathlib import Path
import shutil
from bc_common import ROOT,SOURCE,HERE,read,write,sha


def main(root):
    assert read(root/'native-verification.json')['complete'];selected=read(root/'preselected.json')['selected']
    for name in ['parent','spec']:
        folder=root/'export'/name;before=sha(folder/'model.mkqb');schema=read(SOURCE/'wire-format.json')
        schema['experiment']='semantic-spec-selfcheck-v1';schema['role']=name
        schema['literal_pool_training']='dynamic full/extras permutations and distractors'if name=='spec'and selected['step']else'unchanged previous SPEC'
        schema['generated_spec_is_not_confirmation_of_request']=True;write(folder/'wire-format.json',schema)
        runtime=folder/'protocol-source';runtime.mkdir(exist_ok=True)
        for n in ['ay_codec.py','ay_runtime.py','az_runtime.py','ay_chat.py','az_chat.py','az_teacher.py','ay_teacher.py','ax_completion.py']:
            shutil.copyfile(HERE/n,runtime/n)
        write(folder/'protocol-source-sha256.json',{p.name:sha(p)for p in runtime.iterdir()if p.is_file()})
        manifest=read(folder/'manifest.json');manifest.update(experiment='semantic-spec-selfcheck-v1',role=name,
           parent_packet_sha256=sha(SOURCE/'model.mkqb'));write(folder/'manifest.json',manifest)
        assert sha(folder/'model.mkqb')==before


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
