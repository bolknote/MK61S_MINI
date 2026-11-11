"""Continuation of both 3M branches: literals, new numbers, complete RUN cycles."""
from ay_common import HERE,REPO,ARMS,ACTIONS,ACTION_IDS,CORRECT_IDS,END,MAX_TURNS,body_ids,output_ids,compact_head,read,rows,write,save_rows,sha

ROOT=REPO/'.build/mk61-agent-20261106/semantic-spec-distill-v2'
PARENT=ROOT.parent/'semantic-spec-distill-v1'
PARENT=PARENT if(PARENT/'export/hex/model.mkqb').exists()else PARENT/'server-results'
SOURCES={a:PARENT/'export'/a for a in ARMS}
DEV_NUMBERS=['0.35','0.65','7.25','13','26','33.5','57','68','85.5']
TEST_NUMBERS=['0.45','0.85','11.75','17','29.5','41','53.25','67','79.5']
TRAIN_NUMBERS=['0.125','0.2','0.375','0.5','0.75','1.25','1.5','2.25','2.5','3.5','4.25','5','6.25','6.5','8','9.25',
               '12','14.5','15','18.5','20','22','24','27.5','30','35','40','45','50','60','70','75','80','90','-3','-7.5','-12','-22']


def check_frozen():
    f=read(ROOT/'frozen.json')
    for n,d in f['sources'].items():assert sha(HERE/n)==d,n
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    for arm,files in f['parents'].items():
        for name,digest in files.items():assert sha(SOURCES[arm]/name)==digest,(arm,name)
    for name,digest in f['external_sources'].items():assert sha(REPO/name)==digest,name
    from ay_common import INITIAL
    for name,digest in f['foundation_files'].items():assert sha(INITIAL/name)==digest,name
    return f
