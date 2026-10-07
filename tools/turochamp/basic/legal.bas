:again
CALL pseudo :candidate
:candidate
IF GLMOVE=0 G.:done
IF GLMODE<4 G.:test_move
F=GLMOVE MOD 128;T=INT(GLMOVE/128) MOD 128
B=(@(T)#0) OR (INT(GLMOVE/16384)>0)
IF ABS(@(F))=1 IF T=EP B=1
IF GLMODE=4 IF B=0 G.:again
IF GLMODE=5 IF B=1 G.:again
:test_move
APMOVE=GLMOVE;APFRAME=G_UNDO
LOCAL make
:test
AQ=WK;IF GLSIDE=-1 AQ=BK
AS=-GLSIDE
LOCAL attack
:tested
TMP=AT;APFRAME=G_UNDO
CALL unmake :restored
:restored
IF TMP>0 G.:again
:done
RET
