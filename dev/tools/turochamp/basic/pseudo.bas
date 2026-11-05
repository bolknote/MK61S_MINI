:start
A=@(GLSTATE);F=A MOD 128;D=INT(A/128) MOD 16;R=INT(A/2048) MOD 8+1
IF F=0 F=21:IF GLPIECE>0 F=GLPIECE
IF A=0 @(GLSTATE)=F
IF F>=99 G.:end
IF GLPIECE>0 IF F>GLPIECE G.:end
B=@(F);IF (B*GLSIDE<=0) OR (ABS(B)>6) G.:next_piece
IF GLPIECE>0 IF F#GLPIECE G.:next_piece
K=ABS(B);IF GLTYPE>0 K=GLTYPE
IF K=1 G.:pawn
IF D>=8 G.:castle
Z=@(DIRS+D);IF K=2 Z=@(DIRN+D)
IF K=3 IF ABS(Z)#9 IF ABS(Z)#11 G.:next_direction
IF K=4 IF ABS(Z)#1 IF ABS(Z)#10 G.:next_direction
T=F+Z*R;C=@(T)
IF (ABS(C)>6) OR (C*GLSIDE>0) G.:next_direction
IF GLMODE#3 IF ABS(C)=6 G.:next_direction
GLMOVE=F+128*T
IF (K=2) OR (K=6) OR (C#0) G.:yield_direction
IF R=7 G.:yield_direction
@(GLSTATE)=F+128*D+2048*R
RET
:yield_direction
@(GLSTATE)=F+128*(D+1)
RET
:pawn
LOCAL pawns
:pawn_done
IF GLMOVE>0 G.:return
G.:start
:castle
IF (K#6) OR (GLMODE=3) G.:next_piece
IF D>=10 G.:next_piece
CALL castle :castle_done
:castle_done
IF GLMOVE>0 G.:return
G.:start
:return
RET
:next_direction
@(GLSTATE)=F+128*(D+1);G.:start
:next_piece
@(GLSTATE)=F+1;G.:start
:end
GLMOVE=0
RET
