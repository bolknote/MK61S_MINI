IF UI_PHASE=1 G.:game_menu
UI_ACTION=0
:start
C.:P."ТУРОЧЕМП":P."ВЫБЕРИТЕ СТОРОНУ"
IF UI_ACTION=0 P."БЕЛЫЕ"
IF UI_ACTION=1 P."ЧЁРНЫЕ"
IF UI_ACTION=2 P."ДВА ИГРОКА"
IF UI_ACTION=3 P."ИНСТРУКЦИЯ"
P."СТРЕЛКИ - ВЫБОР":P."ОК - НАЧАТЬ"
UI_KEY=INP.()
IF (UI_KEY=15) OR (UI_KEY=17) UI_ACTION=(UI_ACTION+3) MOD 4
IF (UI_KEY=16) OR (UI_KEY=18) UI_ACTION=(UI_ACTION+1) MOD 4
IF UI_KEY#19 G.:start
IF UI_ACTION=3 G.:help
MODE=(UI_ACTION=0)-(UI_ACTION=1);UI_VIEW=MODE
IF MODE=0 UI_VIEW=1
CUR=35;IF MODE=-1 CUR=85
JUMP game
:game_menu
C.:P."МЕНЮ ПАРТИИ"
IF UI_ACTION=0 P."ВЕРНУТЬСЯ"
IF UI_ACTION=1 P."ЗАЯВИТЬ НИЧЬЮ"
IF UI_ACTION=2 P."ПРЕДЛОЖИТЬ НИЧЬЮ"
IF UI_ACTION=3 P."СДАТЬСЯ"
IF UI_ACTION=4 P."НОВАЯ ИГРА"
P."СТРЕЛКИ - ВЫБОР":P."ОК - ПОДТВЕРДИТЬ":P."СХ - НАЗАД"
UI_KEY=INP.()
IF (UI_KEY=15) OR (UI_KEY=17) UI_ACTION=(UI_ACTION+4) MOD 5
IF (UI_KEY=16) OR (UI_KEY=18) UI_ACTION=(UI_ACTION+1) MOD 5
IF UI_KEY=22 G.:back
IF UI_KEY#19 G.:game_menu
ON UI_ACTION+1 G.:back,:claim,:offer,:resign,:new
:resign
RESULT=(SIDE=-1)+2*(SIDE=1);DRAW_REASON=9
JUMP result
:claim
JUMP claim
:offer
IF MODE=0 G.:ask_offer
IF (-MODE)*(MATW-MATB)<=0 G.:draw
C.:P."ТУРОЧЕМП ОТКЛОНИЛ НИЧЬЮ":P."ОК - НАЗАД":PAU.
G.:back
:ask_offer
C.:P."ПРЕДЛОЖЕНА НИЧЬЯ":P."СОПЕРНИК: ОК - ПРИНЯТЬ":P."СХ - ОТКЛОНИТЬ"
UI_KEY=INP.()
IF UI_KEY=19 G.:draw
IF UI_KEY#22 G.:ask_offer
G.:back
:draw
RESULT=9;DRAW_REASON=9
JUMP result
:new
JUMP init
:back
JUMP game
:help
CALL help :helped
:helped
UI_ACTION=0;G.:start
