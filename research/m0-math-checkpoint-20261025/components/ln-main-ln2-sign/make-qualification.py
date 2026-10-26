from pathlib import Path
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
s=(ROOT/'.build/m0-ln-near-q77-linear-20261024/qualify.py').read_text()
s=s.replace("BASE=ROOT/'.build/m0-ln-raw-cold-entry-20261024'","BASE=ROOT/'.build/m0-ln-near-q77-linear-20261024'")
a=s.index('previous_trial=json.loads(');z=s.index('states = {',a)
s=s[:a]+s[z:]
s=s.replace(';retained_trial=0','')
a=s.index('        saved_trial=trial_previous.get(');z=s.index('        rows.append(',a)
s=s[:a]+s[z:]
s=s.replace("assert retained==len(parent['rows'])==97998","assert retained==len(parent['rows'])==118044")
for line in ("assert retained_trial==len(previous_trial['rows'])==114766\n","report['retained_control_counts_from_previous_full_trial']=retained_trial\n","report['previous_trial_candidate_not_used_as_parent']=True\n"):
    assert line in s;s=s.replace(line,'')
a=s.index('states = {')
extra="""for row in parent['remaining_slower_correct_Qfplib']:
    if row['SIO']=='READY':
        for step in range(-64,65):add(int(row['x'],16)+step,'remaining_main_neighbors')
rng=random.Random(0x1A2B170)
for _ in range(1024):
    k=rng.choice((-1022,-512,-32,-31,-2,-1,1,2,31,32,512,1023))
    add(((k+1023)<<52)+rng.randrange(1<<52),'main_exponent_controls')
"""
s=s[:a]+extra+s[a:]
s=s.replace('PASS_Q77_LINEAR_NEAR_LN_ALL_PROFILED_NOT_PRODUCTION','PASS_MAIN_LN_LN2_DIRECTION_ALL_PROFILED_NOT_PRODUCTION')
(W/'qualify.py').write_text(s)
