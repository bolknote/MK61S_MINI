IF RESULT>0 G.:result
REPDEP=0
CALL status :status
:status
IF STAT>0 RESULT=STAT:DRAW_REASON=STAT:G.:end
IF MODE=0 G.:human
IF SIDE=MODE G.:human
UI_MESSAGE=1
CALL board :thinking
:thinking
CALL search :computer
:computer
IF BEST>0 MOVE=BEST:G.:move
RESULT=7;IF INT(SIM/2) MOD 2=1 RESULT=8
DRAW_REASON=RESULT;G.:end
:human
UI_MESSAGE=0;UI_VIEW=MODE
IF MODE=0 UI_VIEW=SIDE
:show
CALL board :key
:key
UI_MESSAGE=0
IF UI_KEY=21 UI_PHASE=1:UI_ACTION=0:G.:menu
IF UI_KEY=25 G.:help
IF UI_KEY=22 SEL=0:G.:show
D=0
IF UI_KEY=15 D=-UI_VIEW
IF UI_KEY=16 D=UI_VIEW
IF UI_KEY=17 D=10*UI_VIEW
IF UI_KEY=18 D=-10*UI_VIEW
IF D=0 G.:choose
T=CUR+D;IF ABS(@(T))<=6 CUR=T
G.:show
:choose
IF UI_KEY#19 G.:show
IF @(CUR)*SIDE>0 SEL=CUR:G.:show
IF SEL=0 G.:show
PROMO=0;IF ABS(@(SEL))=1 IF INT(CUR/10)=9*(SIDE=1)+2*(SIDE=-1) G.:promotion
MOVE=SEL+128*CUR
:move
APSIDE=0
CALL turn :moved
:moved
IF RETVAL=0 UI_MESSAGE=3:G.:show
SEL=0
G.:restart
:restart
JUMP game
:promotion
APSIDE=1;MOVE=SEL+128*CUR+16384*5
CALL turn :promotable
:promotable
APSIDE=0
IF RETVAL=0 UI_MESSAGE=3:G.:show
JUMP promote
:menu
JUMP menu
:help
CALL help :helped
:helped
G.:show
:end
G.:result
:result
UI_MESSAGE=4
:result_show
CALL board :result_key
:result_key
IF UI_KEY#19 G.:result_show
JUMP init
