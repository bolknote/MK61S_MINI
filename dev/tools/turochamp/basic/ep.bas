RETVAL=0
IF EP=0 G.:done
IF @(EP)#0 G.:done
IF @(EP-10*SIDE)#-SIDE G.:done
@(RP_META+4)=0
:candidate
@(RP_META)=EP-(9+2*@(RP_META+4))*SIDE
A=@(RP_META)
IF @(A)#SIDE G.:next
@(A)=0;@(EP)=SIDE;@(EP-10*SIDE)=0
AQ=WK;IF SIDE=-1 AQ=BK
AS=-SIDE
LOCAL attack
:tested
A=@(RP_META);@(A)=SIDE;@(EP)=0;@(EP-10*SIDE)=-SIDE
IF AT=0 RETVAL=EP
IF AT=0 G.:done
:next
@(RP_META+4)=@(RP_META+4)+1
IF @(RP_META+4)<2 G.:candidate
:done
RET
