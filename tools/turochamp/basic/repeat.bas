RP_COUNT=1;RP_DEPTH=REPDEP;RP_BACK=REPDEP
IF EP>0 G.:done
RP_BRANCH=0
CALL rkey :snapshot
:snapshot
IF RP_BACK=0 G.:history
:search_back
F=STACK+7*(RP_BACK-1)+1;U=@(F);M=U MOD 131072;T=INT(M/128) MOD 128
C=INT(U/131072) MOD 16-6
IF (INT(M/16384)>0) OR (ABS(@(T))=1) OR (C#0) OR (@(F+1) MOD 16#RIGHTS) G.:search_forward
APFRAME=F
CALL unmake :search_undone
:search_undone
RP_BACK=RP_BACK-1;RP_BRANCH=1
CALL rkey :search_compared
:search_compared
RP_COUNT=RP_COUNT+REPRESULT
IF RP_BACK>0 G.:search_back
:history
RP_HCUR=HCOUNT
:history_back
IF RP_HCUR=0 G.:history_forward
RP_BRANCH=2
CALL rstep :history_undone
:history_undone
RP_BRANCH=1
CALL rkey :history_compared
:history_compared
RP_COUNT=RP_COUNT+REPRESULT;G.:history_back
:history_forward
IF RP_HCUR>=HCOUNT G.:search_forward
RP_BRANCH=3
CALL rstep :history_redone
:history_redone
G.:history_forward
:search_forward
IF RP_BACK>=RP_DEPTH G.:done
APMOVE=@(STACK+7*RP_BACK+1) MOD 131072;APFRAME=G_UNDO
CALL make :search_redone
:search_redone
RP_BACK=RP_BACK+1;G.:search_forward
:done
REPRESULT=RP_COUNT
RET
