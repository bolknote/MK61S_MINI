import copy
from hil_chess_screen_mode import sample,checked,r0,summary,MODES,PROBE_FILES

raw='PROF state=stopped clock=96000000\nKEYWAIT sequence=7 us=22000001 key=37 screen_begin=0 screen_end=0\r\n'
after=sample(raw);before=dict(after,sequence=6)
assert checked(before,after,'headless')==22.000001
assert checked(dict(before,sequence=0),dict(after,sequence=8),'headless',8)==22.000001
assert checked(dict(before,sequence=8),dict(after,sequence=17),'headless',9)==22.000001
for field,value in (('sequence',6),('key',39),('us',0),('screen_begin',1),('screen_end',1)):
    damaged=dict(after,**{field:value})
    try:checked(before,damaged,'headless')
    except AssertionError:pass
    else:raise AssertionError('accepted invalid '+field)
on=dict(after,screen_begin=1,screen_end=1)
assert checked(before,on,'continuous')==22.000001
for invalid in (raw.replace('stopped','running'),raw.replace('KEYWAIT','MISSING'),raw.replace('screen_end=0','screen_end=2')):
    try:sample(invalid)
    except AssertionError:pass
    else:raise AssertionError('accepted missing/invalid timing record')
assert r0('R0 =  4.2000000  02\r\n')==420
assert r0('R0 = -4.2000000 -02\r\n')==-.042
assert r0('R0 =  0.0000000  00\r\n')==0
runs=[dict(screen_mode=mode,seconds=value) for mode,value in zip(MODES,(99,88,25,22,22.2,25.2))]
out=summary([dict(name='test',runs=runs)])[0]
assert out['samples']==dict(continuous=[25,25.2],headless=[22,22.2])
assert out['continuous_seconds']==25.1 and out['headless_seconds']==22.1
broken=copy.deepcopy(runs);broken[3]['screen_mode']='continuous'
try:summary([dict(name='broken',runs=broken)])
except AssertionError:pass
else:raise AssertionError('accepted missing/mixed USB cohort')
assert PROBE_FILES['__bench.tbi']==b'10 .R0=@(146);END\n'
print('Headless chess: MCU timing boundaries, screen-off guards, node probe and unmixed on/off cohorts PASS')
