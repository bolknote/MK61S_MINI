UI_ITER=0
:candidate
GLSTATE=&UI_ITER;GLSIDE=SIDE;GLMODE=2;GLPIECE=MOVE MOD 128;GLTYPE=0
CALL legal :tested
:tested
IF GLMOVE=0 RETVAL=0:G.:done
IF GLMOVE#MOVE G.:candidate
IF APSIDE>0 RETVAL=1:G.:done
APMOVE=MOVE;APFRAME=ROOTTMP
CALL make :made
:made
CALL history :remembered
:remembered
RETVAL=1
:done
RET
