:node
NODES=NODES+1;REPDEP=DFS
CALL status :status
:status
IF STAT>0 G.:terminal
IF DFS>=QLIMIT G.:leaf
F=STACK+7*DFS;SEARCH_CUR=F
@(F)=0;@(F+3)=-100000;@(F+4)=ALPHA;@(F+5)=LFRAME;@(F+6)=CHECK+8*CLAIM
IF CLAIM>0 @(F+3)=0
IF DFS<LEVEL G.:ready
IF CHECK=1 G.:ready
IF @(STACK+7*(DFS-1)+6) MOD 2=1 G.:selective
IF LASTCAP=0 G.:leaf
AQ=LASTCAP;AS=SIDE
LOCAL attack
:recapture
IF AT=0 G.:leaf
:selective
F=STACK+7*DFS
@(F+6)=@(F+6)+4;A=SIDE*(MATW-MATB)
IF A>@(F+3) @(F+3)=A
IF @(F+3)>@(F+4) @(F+4)=@(F+3)
IF @(F+4)>=@(F+5) G.:cut
:ready
G.:walk
:cut
RETVAL=@(F+3);DRAW_REASON=INT(@(F+6)/8) MOD 4;SEARCH_CUR=-1
G.:walk
:leaf
RETVAL=SIDE*(MATW-MATB)
IF CLAIM>0 IF RETVAL<0 RETVAL=0
DRAW_REASON=CLAIM;SEARCH_CUR=-1
G.:walk
:terminal
RETVAL=0;DRAW_REASON=0
IF STAT<3 RETVAL=-2000+DFS
SEARCH_CUR=-1
G.:walk
:walk
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
G.:node
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
