CALL claims :found
:found
IF CLAIM=0 G.:unavailable
C.:P."МОЖНО ЗАЯВИТЬ НИЧЬЮ"
IF H_MOVE=0 G.:confirm
P."ОБЪЯВЛЕННЫЙ ХОД:"
W=H_MOVE MOD 128:GOS.:coord
P."-";:W=INT(H_MOVE/128) MOD 128:GOS.:coord
P.
:confirm
P."ОК - ЗАЯВИТЬ":P."СХ - НАЗАД"
UI_KEY=INP.()
IF UI_KEY=22 G.:back
IF UI_KEY#19 G.:confirm
RESULT=7;IF INT(CLAIM/2) MOD 2=1 RESULT=8
DRAW_REASON=RESULT
JUMP game
:unavailable
C.:P."НЕТ ОСНОВАНИЙ ДЛЯ НИЧЬЕЙ":P."ОК - НАЗАД":PAU.
:back
JUMP game
:coord
F=W MOD 10
IF F=1 P."a";
IF F=2 P."b";
IF F=3 P."c";
IF F=4 P."d";
IF F=5 P."e";
IF F=6 P."f";
IF F=7 P."g";
IF F=8 P."h";
P.#0,INT(W/10)-1;:R.
