"""Outer supervisor for exactly one Root-authorized all-eight campaign."""
import argparse,json,os,sys,time
from pathlib import Path
import campaign
from supervisor import run_once
def main():
    p=argparse.ArgumentParser();p.add_argument('--campaign-go',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    go,_,_=campaign.precheck(a.campaign_go)
    argv=[go['python'],str(Path(__file__).with_name('campaign.py')),'--campaign-go',str(a.campaign_go),'--output',str(a.output/'campaign')]
    remaining=go['finish_before_utc_epoch']-time.time();assert 0<remaining<=10800
    r=run_once(argv,a.output/'outer-process',cwd=go['cwd'],env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),timeout_seconds=min(10800,remaining+2),max_log_bytes=16*1048576)
    print(json.dumps(r,indent=2));assert r['status']=='PASS_PROCESS_EXIT'
if __name__=='__main__':main()
