A=@(GLSTATE);F=A MOD 128;D=INT(A/128) MOD 16;S=GLSIDE
GLMOVE=0
IF F#25*(S=1)+95*(S=-1) G.:next
B=1*(S=1)+4*(S=-1);Z=1
IF D=8 B=B*2:Z=-1
IF INT(RIGHTS/B) MOD 2=0 G.:next
R=F+3;IF D=8 R=F-4
IF @(R)#4*S G.:next
IF (@(F+Z)#0) OR (@(F+2*Z)#0) G.:next
IF D=8 IF @(F-3)#0 G.:next
GLMOVE=F+128*(F+2*Z);AQ=F;AS=-S
LOCAL attack
:origin
IF AT>0 G.:bad
F=GLMOVE MOD 128;T=INT(GLMOVE/128);AQ=(F+T)/2;AS=-GLSIDE
LOCAL attack
:transit
IF AT>0 G.:bad
AQ=INT(GLMOVE/128);AS=-GLSIDE
LOCAL attack
:destination
IF AT>0 G.:bad
G.:next
:bad
GLMOVE=0
:next
A=@(GLSTATE);F=A MOD 128;D=INT(A/128) MOD 16
@(GLSTATE)=F+128*(D+1)
RET
