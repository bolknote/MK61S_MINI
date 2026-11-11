"""Attach inference protocol receipts without changing any audited weight byte."""
import argparse
import json
from pathlib import Path
import shutil
from ay_codec import UNARY_NAMES,BINARY_NAMES
from ay_teacher import pool_for
from ay_common import HERE,write,sha


def main(root):
    assert json.loads((root/'native-verification.json').read_text())['complete']
    for arm in ['hex','spec']:
        folder=root/'export'/arm;before=sha(folder/'model.mkqb')
        schema={'version':'semantic-spec-distill-v1','output_arm':arm,'angle':'supplied by harness',
                'constant_pool':{'base':pool_for(''),'additional':'append unique ha_protocol.constants(task), preserving order',
                                 'indices':'unsigned bytes 00..FF','implementation':'ay_teacher.pool_for'},
                'HEX':'ordinary MK-61 plus FF 00 raw FF, FF 01 kk constant, FF 02 ll label, FF 03 ll address',
                'SPEC':{'destination':'FF = preserve memory; 00..0E = store X in register',
                        'expression':'one prefix tree after destination; no trailing bytes',
                        'register_leaves':'00..0E refer to initial R0..RE','constant_leaf':'10 kk','pi_leaf':'11',
                        'unary':{f'{0x20+i:02X}':n for i,n in enumerate(UNARY_NAMES)},
                        'binary':{f'{0x40+i:02X}':n for i,n in enumerate(BINARY_NAMES)},'max_nodes':31},
                'deployed_to_firmware':False,'generated_spec_is_not_confirmation_of_request':True}
        write(folder/'wire-format.json',schema)
        runtime=folder/'protocol-source';runtime.mkdir(exist_ok=True)
        for name in ['ay_codec.py','ay_runtime.py','ay_chat.py','ax_completion.py']:
            shutil.copyfile(HERE/name,runtime/name)
        write(folder/'protocol-source-sha256.json',{p.name:sha(p)for p in runtime.iterdir()if p.is_file()})
        assert sha(folder/'model.mkqb')==before
    print('Audited weights retained; constant-pool and output-codec policies attached')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root.resolve())
