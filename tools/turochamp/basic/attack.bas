# Reverse attacks from the target; pinned pieces still attack for king safety.
AT=0;AN=0;TMP=0
FOR I=0 TO 7
D=@(DIRS+I);J=AQ+D;N=1
:ray
P=@(J);K=ABS(P)
IF K>6 G.:next
IF K=0 J=J+D:N=N+1:G.:ray
IF P*AS<=0 G.:next
IF K=5 G.:hit
IF K=3 IF (ABS(D)=9) OR (ABS(D)=11) G.:hit
IF K=4 IF (ABS(D)=1) OR (ABS(D)=10) G.:hit
IF N#1 G.:next
IF K=6 G.:hit
IF K=1 IF (D=-9*AS) OR (D=-11*AS) G.:hit
G.:next
:hit
AT=AT+1;IF K#1 AN=AN+1
TMP=J
:next
J=AQ+@(DIRN+I)
IF @(J)=2*AS AT=AT+1:AN=AN+1:TMP=J
NEXT I
RET
