from pathlib import Path
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
s=(ROOT/'.build/m0-ln-near-q77-products-20261024/qualify.py').read_text()
a=s.index('states = {')
extra="""previous_trial=json.loads((ROOT/'.build/m0-ln-near-q77-products-20261024/qualification.json').read_text())
trial_previous={(r['x'],r['SIO']):r for r in previous_trial['rows']}
for row in previous_trial['rows']:
    if row['SIO']=='READY':add(int(row['x'],16),row['group'])
for row in previous_trial['remaining_slower_correct_Qfplib']:
    for step in range(-8,9):add(int(row['x'],16)+step,'previous_Q77_speed_loss_neighbors')
for index in range(1,257):
    if index==128:continue
    negative=index<128
    n=128-index if negative else index-128
    den=8064+index
    grid=512 if negative else 1024
    for edge in (-grid,0,grid):
        delta=den*1024+edge
        for side in (-1,1):
            a=(n<<49)+side*delta
            raw=0x3ff0000000000000-(a>>9) if negative else 0x3ff0000000000000+(a>>10)
            add(raw,'linear_precision_threshold')
"""
s=s[:a]+extra+s[a:]
s=s.replace('rows=[];start=time.monotonic();retained=0','rows=[];start=time.monotonic();retained=0;retained_trial=0')
anchor="            retained+=1"
assert s.count(anchor)==1
s=s.replace(anchor,anchor+"""
        saved_trial=trial_previous.get((f'{raw:016X}',state_name))
        if saved_trial:
            assert counts['parent']==saved_trial['instructions']['parent']
            assert outputs['parent']==saved_trial['outputs']['parent']
            retained_trial+=1""")
s=s.replace("assert retained==len(parent['rows'])==97998","assert retained==len(parent['rows'])==97998\nassert retained_trial==len(previous_trial['rows'])==114766\nreport['retained_control_counts_from_previous_full_trial']=retained_trial\nreport['previous_trial_candidate_not_used_as_parent']=True")
s=s.replace('PASS_Q77_NEAR_LN_ALL_PROFILED_NOT_PRODUCTION','PASS_Q77_LINEAR_NEAR_LN_ALL_PROFILED_NOT_PRODUCTION')
(W/'qualify.py').write_text(s)
