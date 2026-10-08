#!/usr/bin/env python3
"""Pure workload/marker guards for the timing harness; no device writes."""
from hil_language_vm_speed import cases,marker_pixels

for n in (100,20000,30000):
    samples=cases(n)
    assert len(samples)==8 and sum(x[0]=="foc" for x in samples.values())==3
    assert samples['basic_integer'][2]==sum(i%128+i//128 for i in range(1,n+1))
    for name in ('basic_subroutines','focal_integer','focal_subroutines'):
        assert samples[name][2]==n*(n+1)//2
    assert samples['basic_wide'][2]==589822
    for extension,source,_ in samples.values():
        source=source.replace(';END',';PRINT "VM_DONE";END') if extension=='tbi' else source.replace('1.40 E','1.35 P "VM_DONE"\n1.40 E')
        assert source.count('VM_DONE')==1
        assert len(source.encode('ascii')) < (3584 if extension=='tbi' else 1536)

frame=bytearray(1536);blank=marker_pixels(frame)
for page in range(2):
    for x in range(176,192):frame[page*192+x]=255
assert marker_pixels(frame)==blank
frame[2]=1;assert marker_pixels(frame)!=blank
assert len(marker_pixels(frame))==320
print('VM speed HIL workload values, source quotas, completion markers and disk-overlay exclusion PASS')
