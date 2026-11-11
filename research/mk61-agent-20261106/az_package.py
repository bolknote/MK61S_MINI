"""Attach the updated literal-pool wire contract without changing weights."""
import argparse
from pathlib import Path
import shutil
import ay_package as base
from az_common import HERE,read,write,sha
from az_teacher import pool_for


def main(root):
    base.main(root)
    for arm in ['hex','spec']:
        folder=root/'export'/arm;before=sha(folder/'model.mkqb');schema=read(folder/'wire-format.json')
        schema['version']='semantic-spec-distill-v2'
        schema['constant_pool']={'base':pool_for(''),'additional':'append unique ha_protocol.constants(task), then each explicit literal sign counterpart in order',
            'indices':'unsigned bytes 00..FF','implementation':'az_teacher.pool_for',
            'training_augmentation':'some extras permuted with distractors; ordinary inference uses default order'}
        schema['RUN_contract']='WRITE re-runs active case and invalidates previous runs; RUN 00 and 01 of current revision precede eligible DONE'
        write(folder/'wire-format.json',schema);runtime=folder/'protocol-source'
        for name in ['az_chat.py','az_teacher.py','az_runtime.py','az_common.py']:
            shutil.copyfile(HERE/name,runtime/name)
        write(folder/'protocol-source-sha256.json',{p.name:sha(p)for p in runtime.iterdir()if p.is_file()})
        protocol=read(folder/'protocol.json');protocol['kind']='semantic-spec-distill-v2';protocol['constant_pool']='az_teacher.pool_for'
        write(folder/'protocol.json',protocol);assert sha(folder/'model.mkqb')==before


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
