:start
A=@(GLSTATE);F=A MOD 128;D=INT(A/128) MOD 16;P=INT(A/16384) MOD 4;S=GLSIDE
IF D>=4 @(GLSTATE)=F+1:GLMOVE=0
IF D>=4 G.:return
T=F+10*S
IF D=1 T=F+20*S
IF D=2 T=F+9*S
IF D=3 T=F+11*S
C=@(T);IF ABS(C)>6 G.:next
IF D>=2 G.:capture
IF C#0 G.:next
IF D=0 G.:promotion
IF INT(F/10)#(3*(S=1)+8*(S=-1)) G.:next
IF @(F+10*S)#0 G.:next
G.:promotion
:capture
IF C*S<0 IF ABS(C)#6 G.:promotion
IF (C#0) OR (T#EP) OR (GLSIDE#SIDE) G.:next
IF @(T-10*S)#-S G.:next
:promotion
Q=0;IF INT(T/10)=9*(S=1)+2*(S=-1) Q=5-P
GLMOVE=F+128*T+16384*Q
IF (Q=0) OR (P=3) G.:advance
@(GLSTATE)=F+128*D+16384*(P+1)
G.:return
:advance
@(GLSTATE)=F+128*(D+1)
:return
RET
:next
@(GLSTATE)=F+128*(D+1);G.:start
