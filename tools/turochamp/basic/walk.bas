IF SEARCH_CUR<0 G.:return
:next
F=STACK+7*DFS;GLSTATE=F;GLSIDE=SIDE;GLMODE=2;GLPIECE=0;GLTYPE=0
GLMODE=4+INT(@(F+6)/32) MOD 2
CALL legal :move
:move
F=STACK+7*DFS
IF GLMOVE=0 G.:exhausted
T=INT(GLMOVE/128) MOD 128;P=@(GLMOVE MOD 128)
G.:apply
:exhausted
IF INT(@(F+6)/4) MOD 2=1 G.:finish
IF INT(@(F+6)/32) MOD 2=1 G.:finish
@(F)=0;@(F+6)=@(F+6)+32;G.:next
:apply
APMOVE=GLMOVE;APFRAME=F+1
CALL make :made
:made
F=STACK+7*DFS;ALPHA=-@(F+5);LFRAME=-@(F+4);DFS=DFS+1
JUMP node
:return
IF DFS=1 G.:root
DFS=DFS-1;APFRAME=STACK+7*DFS+1
CALL unmake :restored
:restored
F=STACK+7*DFS;T=-RETVAL
IF DRAW_REASON>0 IF T<0 T=0
IF T>@(F+3) @(F+3)=T
IF T>@(F+4) @(F+4)=T
IF @(F+4)<@(F+5) G.:next
:finish
F=STACK+7*DFS;RETVAL=@(F+3);DRAW_REASON=INT(@(F+6)/8) MOD 4
SEARCH_CUR=-1;G.:return
:root
RET
