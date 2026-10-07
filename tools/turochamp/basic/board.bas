C.
IF UI_VIEW=1 P." abcdefgh  ТУРОЧЕМП"
IF UI_VIEW=-1 P." hgfedcba  ТУРОЧЕМП"
FOR Y=0 TO 7
R=8-Y;IF UI_VIEW=-1 R=Y+1
P.#0,R;
FOR X=1 TO 8
F=X;IF UI_VIEW=-1 F=9-X
W=10*(R+1)+F;T=13*((F+R+1) MOD 2)+@(W)+6
H=(W=CUR) OR (W=SEL)
GOS.:glyph
NEXT X
P." ";
IF Y=0 GOS.:side
IF Y=1 GOS.:state
IF Y=2 GOS.:counter
IF Y=3 P."ОТ ";:W=SEL:GOS.:coord
IF Y=4 P."НА ";:W=CUR:GOS.:coord
IF Y=5 GOS.:last
IF Y=6 P."С/П МЕНЮ";
IF Y=7 P."ОК ";:GOS.:hint
P.
NEXT Y
IF UI_MESSAGE#1 UI_KEY=INP.()
RET
:counter
IF UI_MESSAGE=1 P."ПОЗ ";NODES;:R.
IF UI_MESSAGE=4 G.:reason
P."ХОД ";FULL;:R.
:reason
B=RESULT
IF B<3 IF DRAW_REASON=9 P."СДАЧА";:R.
IF B<3 P."МАТ";:R.
IF B=3 P."ПАТ";:R.
IF B=4 P."НЕТ МАТЕРИАЛА";:R.
IF B=5 P."5 ПОВТОРОВ";:R.
IF B=6 P."75 ХОДОВ";:R.
IF B=7 P."3 ПОВТОРА";:R.
IF B=8 P."50 ХОДОВ";:R.
P."ПО СОГЛАСИЮ";:R.
:side
IF SIDE=1 P."БЕЛЫЕ";:R.
P."ЧЁРНЫЕ";:R.
:state
IF UI_MESSAGE=1 P."ДУМАЕТ...";:R.
IF UI_MESSAGE=2 G.:piece
IF UI_MESSAGE=3 P."НЕЛЬЗЯ";:R.
IF UI_MESSAGE=4 G.:result
IF CHECK=1 P."ШАХ";:R.
P."ВАШ ХОД";:R.
:result
IF RESULT=1 P."БЕЛЫЕ ВЫИГРАЛИ";:R.
IF RESULT=2 P."ЧЁРНЫЕ ПОБЕДИЛИ";:R.
P."НИЧЬЯ";:R.
:piece
IF PROMO=5 P."ФЕРЗЬ";:R.
IF PROMO=4 P."ЛАДЬЯ";:R.
IF PROMO=3 P."СЛОН";:R.
P."КОНЬ";:R.
:hint
IF UI_MESSAGE=4 P."НОВАЯ ИГРА";:R.
IF UI_MESSAGE=2 P."ГОТОВО";:R.
P."ВЫБОР";:R.
:coord
IF W=0 P."-";:R.
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
:last
IF LAST=0 P."ХОД -";:R.
W=LAST MOD 128:GOS.:coord
P."-";:W=INT(LAST/128) MOD 128:GOS.:coord
R.
:glyph
IF H=0 G.:normal
IF T=0 P."а";
IF T=1 P."б";
IF T=2 P."в";
IF T=3 P."г";
IF T=4 P."д";
IF T=5 P."е";
IF T=6 P."ж";
IF T=7 P."з";
IF T=8 P."и";
IF T=9 P."й";
IF T=10 P."к";
IF T=11 P."л";
IF T=12 P."м";
IF T=13 P."н";
IF T=14 P."о";
IF T=15 P."п";
IF T=16 P."р";
IF T=17 P."с";
IF T=18 P."т";
IF T=19 P."у";
IF T=20 P."ф";
IF T=21 P."х";
IF T=22 P."ц";
IF T=23 P."ч";
IF T=24 P."ш";
IF T=25 P."щ";
R.
:normal
IF T=0 P."A";
IF T=1 P."B";
IF T=2 P."C";
IF T=3 P."D";
IF T=4 P."E";
IF T=5 P."F";
IF T=6 P."G";
IF T=7 P."H";
IF T=8 P."I";
IF T=9 P."J";
IF T=10 P."K";
IF T=11 P."L";
IF T=12 P."M";
IF T=13 P."N";
IF T=14 P."O";
IF T=15 P."P";
IF T=16 P."Q";
IF T=17 P."R";
IF T=18 P."S";
IF T=19 P."T";
IF T=20 P."U";
IF T=21 P."V";
IF T=22 P."W";
IF T=23 P."X";
IF T=24 P."Y";
IF T=25 P."Z";
R.
