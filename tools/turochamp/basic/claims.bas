REPDEP=0;H_MOVE=0
CALL status :status
:status
IF (CLAIM>0) OR (STAT>0) G.:done
UI_ITER=0
:candidate
GLSTATE=&UI_ITER;GLSIDE=SIDE;GLMODE=2;GLPIECE=SEL;GLTYPE=0
CALL legal :move
:move
IF GLMOVE=0 G.:done
IF SEL>0 IF INT(GLMOVE/128) MOD 128#CUR G.:candidate
H_MOVE=GLMOVE;APMOVE=GLMOVE;APFRAME=STACK+1
CALL make :made
:made
REPDEP=1
CALL repeat :repetition
:repetition
CLAIM=(REPRESULT>=3)+2*(HALF>=100);APFRAME=STACK+1
CALL unmake :restored
:restored
IF CLAIM=0 G.:candidate
:done
IF CLAIM=0 H_MOVE=0
REPDEP=0
RET
