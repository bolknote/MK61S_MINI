ES=0;EF=21
:piece
IF EF>=99 G.:check
P=@(EF);K=ABS(P)
IF (P*PCS<=0) OR (K>6) G.:next
IF K=1 G.:pawn
ED=0
CALL mobility :mobile
:mobile
ES=ES+INT(10*SQRT(EC)+0.5);K=ABS(@(EF))
IF K=6 G.:king
IF K=5 G.:next
AQ=EF;AS=PCS
LOCAL attack
:defended
IF AT=1 ES=ES+10
IF AT>1 ES=ES+15
G.:next
:king
ED=5
CALL mobility :vulnerable
:vulnerable
ES=ES-INT(10*SQRT(EC)+0.5);G.:next
:pawn
A=INT(EF/10)-3;IF PCS=-1 A=8-INT(EF/10)
ES=ES+2*A;AQ=EF;AS=PCS
LOCAL attack
:pawn_defended
IF AN>0 ES=ES+3
:next
EF=EF+1;G.:piece
:check
AQ=BK;IF PCS=-1 AQ=WK
AS=PCS
LOCAL attack
:checked
ECHECK=(AT>0);ES=ES+5*ECHECK
CALL threat :threatened
:threatened
ES=ES+10*(ETHREAT MOD 2);PE=ES
RET
