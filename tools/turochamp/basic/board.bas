C.
IF UI_VIEW=1 P." abcdefgh  ТУРОЧЕМП" ELSE P." hgfedcba  ТУРОЧЕМП"
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
ON Y+1 GOS.:side,:state,:counter,:from,:to,:last,:menu_hint,:ok_hint
P.
NEXT Y
IF UI_MESSAGE#1 UI_KEY=INP.()
RET
:from
P."ОТ ";:W=SEL:GOS.:coord:R.
:to
P."НА ";:W=CUR:GOS.:coord:R.
:menu_hint
P."С/П МЕНЮ";:R.
:ok_hint
P."ОК ";:GOS.:hint:R.
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
ON F GOS.:file_a,:file_b,:file_c,:file_d,:file_e,:file_f,:file_g,:file_h
P.#0,INT(W/10)-1;:R.
:last
IF LAST=0 P."ХОД -";:R.
W=LAST MOD 128:GOS.:coord
P."-";:W=INT(LAST/128) MOD 128:GOS.:coord
R.
:file_a
P."a";:R.
:file_b
P."b";:R.
:file_c
P."c";:R.
:file_d
P."d";:R.
:file_e
P."e";:R.
:file_f
P."f";:R.
:file_g
P."g";:R.
:file_h
P."h";:R.
:glyph
IF H=0 G.:normal
ON T+1 G.:selected_a,:selected_b,:selected_c,:selected_d,:selected_e,:selected_f,:selected_g,:selected_h,:selected_i,:selected_j,:selected_k,:selected_l,:selected_m,:selected_n,:selected_o,:selected_p,:selected_q,:selected_r,:selected_s,:selected_t,:selected_u,:selected_v,:selected_w,:selected_x,:selected_y,:selected_z
R.
:normal
ON T+1 G.:normal_a,:normal_b,:normal_c,:normal_d,:normal_e,:normal_f,:normal_g,:normal_h,:normal_i,:normal_j,:normal_k,:normal_l,:normal_m,:normal_n,:normal_o,:normal_p,:normal_q,:normal_r,:normal_s,:normal_t,:normal_u,:normal_v,:normal_w,:normal_x,:normal_y,:normal_z
R.
:selected_a
P."а";:R.
:selected_b
P."б";:R.
:selected_c
P."в";:R.
:selected_d
P."г";:R.
:selected_e
P."д";:R.
:selected_f
P."е";:R.
:selected_g
P."ж";:R.
:selected_h
P."з";:R.
:selected_i
P."и";:R.
:selected_j
P."й";:R.
:selected_k
P."к";:R.
:selected_l
P."л";:R.
:selected_m
P."м";:R.
:selected_n
P."н";:R.
:selected_o
P."о";:R.
:selected_p
P."п";:R.
:selected_q
P."р";:R.
:selected_r
P."с";:R.
:selected_s
P."т";:R.
:selected_t
P."у";:R.
:selected_u
P."ф";:R.
:selected_v
P."х";:R.
:selected_w
P."ц";:R.
:selected_x
P."ч";:R.
:selected_y
P."ш";:R.
:selected_z
P."щ";:R.
:normal_a
P."A";:R.
:normal_b
P."B";:R.
:normal_c
P."C";:R.
:normal_d
P."D";:R.
:normal_e
P."E";:R.
:normal_f
P."F";:R.
:normal_g
P."G";:R.
:normal_h
P."H";:R.
:normal_i
P."I";:R.
:normal_j
P."J";:R.
:normal_k
P."K";:R.
:normal_l
P."L";:R.
:normal_m
P."M";:R.
:normal_n
P."N";:R.
:normal_o
P."O";:R.
:normal_p
P."P";:R.
:normal_q
P."Q";:R.
:normal_r
P."R";:R.
:normal_s
P."S";:R.
:normal_t
P."T";:R.
:normal_u
P."U";:R.
:normal_v
P."V";:R.
:normal_w
P."W";:R.
:normal_x
P."X";:R.
:normal_y
P."Y";:R.
:normal_z
P."Z";:R.
