; ECHO-8
; A complete base CHIP-8 first-person story game for a 64x32 display.
;
; State registers survive all rendering and text helpers:
;   V8 room, V9 direction (N/E/S/W), VA mirrors, VB memories,
;   VC story state, VD remaining signal.
;
; Controls: 2 forward, 8 backward, 4/6 turn, 5 interact.

NONE = 255
ROOM_CORE = 11

KEY_FORWARD = 2
KEY_LEFT = 4
KEY_ACTION = 5
KEY_RIGHT = 6
KEY_BACK = 8

ACTION_MIRROR_1 = 1
ACTION_MIRROR_2 = 2
ACTION_MIRROR_3 = 3
ACTION_MEMORY_0 = 16
ACTION_GATE = 48

GLYPH_1 = 28

MSG_TITLE = 0
MSG_INTRO = 1
MSG_MIRROR = 2
MSG_MEMORY = 3
MSG_CORE_OPEN = 4
MSG_REVEAL = 5
MSG_CHOICES = 6
MSG_ESCAPE = 7
MSG_SILENCE = 8
MSG_ECHO = 9
MSG_MISSING = 10
MSG_LOST = 11
MSG_LOCKED = 12

STATE_EXPLORING = 0
STATE_CORE_SEEN = 1
STATE_END_ESCAPE = 225
STATE_END_SILENCE = 226
STATE_END_ECHO = 227

start:
    ld v8, 0
    ld v9, 0
    ld va, 0
    ld vb, 0
    ld vc, STATE_EXPLORING
    ld vd, 99

    ld v7, MSG_TITLE
    call show_message
    ld v7, MSG_INTRO
    call show_message

main_loop:
    call draw_view
    ld v5, k

    ; Ignore keys outside the five game controls without consuming signal.
    se v5, KEY_FORWARD
    jp validate_left
    jp consume_signal
validate_left:
    se v5, KEY_LEFT
    jp validate_action
    jp consume_signal
validate_action:
    se v5, KEY_ACTION
    jp validate_right
    jp consume_signal
validate_right:
    se v5, KEY_RIGHT
    jp validate_back
    jp consume_signal
validate_back:
    se v5, KEY_BACK
    jp main_loop

consume_signal:
    add vd, 255
    se vd, 0
    jp dispatch_key
    ld v7, MSG_LOST
    call show_message
    jp start

dispatch_key:
    se v5, KEY_FORWARD
    jp dispatch_left
    call move_forward
    jp after_action

dispatch_left:
    se v5, KEY_LEFT
    jp dispatch_action
    add v9, 3
    ld v0, 3
    and v9, v0
    jp after_action

dispatch_action:
    se v5, KEY_ACTION
    jp dispatch_right
    call interact
    jp after_action

dispatch_right:
    se v5, KEY_RIGHT
    jp dispatch_back
    add v9, 1
    ld v0, 3
    and v9, v0
    jp after_action

dispatch_back:
    ; Walk backward but preserve the direction in which the player looks.
    ld v0, 2
    xor v9, v0
    call move_forward
    ld v0, 2
    xor v9, v0

after_action:
    se vc, STATE_END_ESCAPE
    jp check_end_silence
    jp start
check_end_silence:
    se vc, STATE_END_SILENCE
    jp check_end_echo
    jp start
check_end_echo:
    se vc, STATE_END_ECHO
    jp main_loop
    jp start


; ---------------------------------------------------------------------------
; Navigation and story actions

move_forward:
    ld v0, v8
    ld v1, v9
    call get_neighbor
    se v0, NONE
    jp move_exists
    call deny_beep
    ret

move_exists:
    ; The final north edge is visible but sealed until all mirrors are active.
    se v0, ROOM_CORE
    jp move_commit
    se va, 7
    jp move_core_locked
    jp move_commit

move_core_locked:
    ld v7, MSG_LOCKED
    call show_message
    ret

move_commit:
    ld v8, v0
    se v8, ROOM_CORE
    ret
    se vc, STATE_EXPLORING
    ret

    ld vc, STATE_CORE_SEEN
    ld v7, MSG_REVEAL
    call show_message
    ld v7, MSG_CHOICES
    call show_message
    call core_menu
    ret

core_menu:
    ld v6, k
    se v6, 2
    jp core_check_silence
    ld vc, STATE_END_ESCAPE
    ld v7, MSG_ESCAPE
    call show_message
    ret

core_check_silence:
    se v6, 4
    jp core_check_echo
    ld vc, STATE_END_SILENCE
    ld v7, MSG_SILENCE
    call show_message
    ret

core_check_echo:
    se v6, 6
    jp core_check_leave
    se vb, 255
    jp core_echo_missing
    ld vc, STATE_END_ECHO
    ld v7, MSG_ECHO
    call show_message
    ret

core_echo_missing:
    ld v7, MSG_MISSING
    call show_message
    jp core_menu

core_check_leave:
    se v6, 8
    jp core_menu
    ld vc, STATE_EXPLORING
    ret


interact:
    call get_action
    se v0, 0
    jp interact_nonempty
    call deny_beep
    ret

interact_nonempty:
    se v0, ACTION_MIRROR_1
    jp interact_mirror_2
    ld v1, 1
    ld v2, GLYPH_1
    jp activate_mirror

interact_mirror_2:
    se v0, ACTION_MIRROR_2
    jp interact_mirror_3
    ld v1, 2
    ld v2, GLYPH_1 + 1
    jp activate_mirror

interact_mirror_3:
    se v0, ACTION_MIRROR_3
    jp interact_gate
    ld v1, 4
    ld v2, GLYPH_1 + 2
    jp activate_mirror

interact_gate:
    se v0, ACTION_GATE
    jp activate_memory
    sne va, 7
    ret
    ld v7, MSG_LOCKED
    call show_message
    ret

activate_mirror:
    ld v0, va
    and v0, v1
    se v0, 0
    ret
    or va, v1

    ld v0, v2
    ld i, mirror_message_digit
    ld [i], v0
    ld v7, MSG_MIRROR
    call show_message

    se va, 7
    ret
    ld v7, MSG_CORE_OPEN
    call show_message
    ret

activate_memory:
    ; Remaining action codes are 0x10..0x17. Convert to an index and bit.
    add v0, 240
    ld v2, v0
    ld i, memory_bits
    add i, v0
    ld v0, [i]

    ld v1, vb
    and v1, v0
    se v1, 0
    ret
    or vb, v0

    ld v0, v2
    add v0, GLYPH_1
    ld i, memory_message_digit
    ld [i], v0
    ld v7, MSG_MEMORY
    call show_message
    ret

deny_beep:
    ld v0, 2
    ld st, v0
    ret


; V0 = room, V1 = direction. Returns the table byte in V0.
get_neighbor:
    shl v0
    shl v0
    add v0, v1
    ld i, neighbors
    add i, v0
    ld v0, [i]
    ret

; Returns the action for the current room and view direction in V0.
get_action:
    ld v0, v8
    shl v0
    shl v0
    add v0, v9
    ld i, actions
    add i, v0
    ld v0, [i]
    ret


; ---------------------------------------------------------------------------
; First-person display

draw_view:
    cls
    ld v0, v8
    ld v1, v9
    call get_neighbor
    se v0, NONE
    jp view_front_open
    ld v0, 0
    jp view_scene_ready

view_front_open:
    ld v2, v0
    ld v0, v2
    ld v1, v9
    call get_neighbor
    se v0, NONE
    jp view_front_deep
    ld v0, 1
    jp view_scene_ready

view_front_deep:
    ld v0, 2

view_scene_ready:
    call draw_scene
    call draw_object
    call draw_hud
    ret


; V0 selects wall, short corridor, or deep corridor.
draw_scene:
    se v0, 0
    jp scene_check_short
    ld i, scene_wall
    jp scene_selected
scene_check_short:
    se v0, 1
    jp scene_deep_selected
    ld i, scene_short
    jp scene_selected
scene_deep_selected:
    ld i, scene_deep

scene_selected:
    ld v2, 0
    ld v3, 0
    ld v4, 15
    ld v5, 8
    ld v6, 15
    ld v7, 9
scene_column:
    drw v2, v3, 15
    add i, v6
    drw v2, v4, 9
    add i, v7
    add v2, 8
    add v5, 255
    se v5, 0
    jp scene_column
    ret


draw_object:
    call get_action
    se v0, 0
    jp object_nonempty
    ret

object_nonempty:
    se v0, ACTION_GATE
    jp object_check_mirror_1
    se va, 7
    jp object_gate_closed
    ret
object_gate_closed:
    ld i, object_gate
    jp object_draw

object_check_mirror_1:
    se v0, ACTION_MIRROR_1
    jp object_check_mirror_2
    ld v1, 1
    jp object_mirror_state
object_check_mirror_2:
    se v0, ACTION_MIRROR_2
    jp object_check_mirror_3
    ld v1, 2
    jp object_mirror_state
object_check_mirror_3:
    se v0, ACTION_MIRROR_3
    jp object_memory_state
    ld v1, 4

object_mirror_state:
    ld v0, va
    and v0, v1
    se v0, 0
    jp object_mirror_active
    ld i, object_mirror_off
    jp object_draw
object_mirror_active:
    ld i, object_mirror_on
    jp object_draw

object_memory_state:
    add v0, 240
    ld i, memory_bits
    add i, v0
    ld v0, [i]
    ld v1, vb
    and v1, v0
    se v1, 0
    jp object_memory_found
    ld i, object_memory
    jp object_draw
object_memory_found:
    ld i, object_memory_empty

object_draw:
    ; Objects occupy a deliberately empty 16x15 window in the scene. Drawing
    ; each half separately keeps this compatible with original CHIP-8 DXYN.
    ld v2, 24
    ld v3, 5
    drw v2, v3, 15
    ld v0, 15
    add i, v0
    ld v2, 32
    drw v2, v3, 15
    ret


draw_hud:
    ; Eight memory lamps, one per recovered ECHO body.
    ld i, hud_memory
    ld v0, vb
    ld v1, 2
    ld v2, 29
    ld v3, 8
    ld v5, 1
hud_memory_loop:
    ld v4, v0
    and v4, v5
    se v4, 0
    drw v1, v2, 1
    shr v0
    add v1, 3
    add v3, 255
    se v3, 0
    jp hud_memory_loop

    ; Three wider mirror lamps.
    ld i, hud_mirror
    ld v0, va
    ld v1, 29
    ld v2, 28
    ld v3, 3
hud_mirror_loop:
    ld v4, v0
    and v4, v5
    se v4, 0
    drw v1, v2, 1
    shr v0
    add v1, 5
    add v3, 255
    se v3, 0
    jp hud_mirror_loop

    ; Decimal signal budget.
    ld i, bcd_buffer
    ld v0, vd
    ld b, v0
    ld v2, [i]
    ld v3, 47
    ld v4, 26
    ld f, v1
    drw v3, v4, 5
    add v3, 5
    ld f, v2
    drw v3, v4, 5

    ; Five-pixel compass arrow.
    ld v0, v9
    ld v1, v0
    shl v0
    shl v0
    add v0, v1
    ld i, compass
    add i, v0
    ld v2, 58
    ld v3, 26
    drw v2, v3, 5
    ret


; ---------------------------------------------------------------------------
; Text display. V7 is a message number; game state V8..VD is preserved.

show_message:
    cls
    ld i, message_offsets
    add i, v7
    ld v0, [i]
    ld v6, v0
    ld v4, 0
    ld v5, 3

message_loop:
    ld i, messages
    add i, v6
    ld v0, [i]
    se v0, 255
    jp message_not_end
    ld v0, k
    ret

message_not_end:
    se v0, 254
    jp message_glyph
    ld v4, 0
    add v5, 8
    add v6, 1
    jp message_loop

message_glyph:
    ld v1, v0
    shl v0
    shl v0
    add v0, v1
    ld i, font_data
    add i, v0
    drw v4, v5, 5
    add v4, 4
    add v6, 1
    jp message_loop


; ---------------------------------------------------------------------------
; World tables: four bytes per room, ordered north/east/south/west.

neighbors:
    .byte 1, NONE, NONE, 9
    .byte 2, 3, 0, 4
    .byte 5, NONE, 1, NONE
    .byte 6, 7, NONE, 1
    .byte 8, 1, 9, NONE
    .byte NONE, 6, 2, 8
    .byte 10, NONE, 3, 5
    .byte NONE, NONE, NONE, 3
    .byte NONE, 5, 4, NONE
    .byte 4, 0, NONE, NONE
    .byte 11, NONE, 6, NONE
    .byte NONE, NONE, 10, NONE

actions:
    .byte 0, ACTION_MEMORY_0, 0, 0
    .byte 0, 0, 0, 0
    .byte 0, ACTION_MIRROR_1, 0, 0
    .byte 0, 0, ACTION_MEMORY_0 + 1, 0
    .byte 0, 0, 0, ACTION_MEMORY_0 + 2
    .byte ACTION_MEMORY_0 + 3, 0, 0, 0
    .byte 0, ACTION_MEMORY_0 + 4, 0, 0
    .byte ACTION_MEMORY_0 + 5, ACTION_MIRROR_2, 0, 0
    .byte ACTION_MEMORY_0 + 6, 0, 0, ACTION_MIRROR_3
    .byte 0, 0, ACTION_MEMORY_0 + 7, 0
    .byte ACTION_GATE, 0, 0, 0
    .byte 0, 0, 0, 0

memory_bits:
    .byte 1, 2, 4, 8, 16, 32, 64, 128

bcd_buffer:
    .byte 0, 0, 0


; ---------------------------------------------------------------------------
; Perspective scenes, packed by 8-pixel column for two DXYN calls per column.

scene_wall:
    .bitmap64
################################################################
#.###......................................................###.#
#....###................................................###....#
#.......################################################.......#
#.......#............######################............#.......#
#.......#............#....................#............#.......#
#.......#............#....................#............#.......#
#.......#............#....................#............#.......#
#.......#............#....................#............#.......#
#.......#............#....................#............#.......#
#.......#............#....................#............#.......#
#.......#............#....................#............#.......#
#.......#............#....................#............#.......#
#.......#............#....................#............#.......#
#.......#............#....................#............#.......#
#.......#............#....................#............#.......#
#.......#............#....................#............#.......#
#.......#............######################............#.......#
#.......################################################.......#
#....###................................................###....#
#.###......................................................###.#
################################################################
    .end

scene_short:
    .bitmap64
################################################################
#.###......................................................###.#
#....###................................................###....#
#.......###..........................................###.......#
#..........##########################################..........#
#...........#.###..............................###.#...........#
#...........#....##..........................##....#...........#
#...........#......###....................###......#...........#
#...........#.........##................##.........#...........#
#...........#..........#................#..........#...........#
#...........#..........#................#..........#...........#
#...........#..........#................#..........#...........#
#...........#..........#................#..........#...........#
#...........#..........#................#..........#...........#
#...........#..........#................#..........#...........#
#...........#..........#................#..........#...........#
#...........#.........##................##.........#...........#
#...........#.....####....................####.....#...........#
#...........#.####............................####.#...........#
#..........#############................#############..........#
#.......###..........................................###.......#
#....###................................................###....#
#.###......................................................###.#
################################################################
    .end

scene_deep:
    .bitmap64
################################################################
#.###......................................................###.#
#....###................................................###....#
#.......###..........................................###.......#
#..........##########################################..........#
#...........#.###..............................###.#...........#
#...........#....##..........................##....#...........#
#...........#......###....................###......#...........#
#...........#.........####################.........#...........#
#...........#..........#.##..........##.#..........#...........#
#...........#..........#...##########...#..........#...........#
#...........#..........#....#......#....#..........#...........#
#...........#..........#....#......#....#..........#...........#
#...........#..........#....#......#....#..........#...........#
#...........#..........#...##########...#..........#...........#
#...........#..........#.##..........##.#..........#...........#
#...........#.........####################.........#...........#
#...........#.....####....................####.....#...........#
#...........#.####............................####.#...........#
#..........##########################################..........#
#.......###..........................................###.......#
#....###................................................###....#
#.###......................................................###.#
################################################################
    .end


; ---------------------------------------------------------------------------
; Objects and HUD sprites.

object_mirror_off:
    .bitmap16
.......##.......
......#..#......
.....#....#.....
....#......#....
...#........#...
..#..........#..
...#........#...
....#......#....
.....#....#.....
......#..#......
.......##.......
.......##.......
....########....
......#..#......
.....#....#.....
    .end
object_mirror_on:
    .bitmap16
#......##......#
.#....####....#.
..#..######..#..
...##########...
..############..
.##############.
..############..
...##########...
....########....
.....######.....
......####......
.......##.......
....########....
......#..#......
.....#....#.....
    .end
object_memory:
    .bitmap16
....########....
...#........#...
...#...##...#...
...#..####..#...
...#...##...#...
...#...##...#...
...#..####..#...
...#.#.##.#.#...
...#...##...#...
...#...##...#...
...#..#..#..#...
...#..#..#..#...
...#........#...
....########....
......####......
    .end
object_memory_empty:
    .bitmap16
....########....
...#........#...
...#.#....#.#...
...#..#..#..#...
...#...##...#...
...#........#...
...#........#...
...#....#...#...
...#...#....#...
...#..#.....#...
...#........#...
...#........#...
...#........#...
....########....
......####......
    .end
object_gate:
    .bitmap16
..############..
..#..........#..
..#.#..##..#.#..
..#.#..##..#.#..
..#.#..##..#.#..
..#.#..##..#.#..
..#.#..##..#.#..
..#.#..##..#.#..
..#.#..##..#.#..
..#.#..##..#.#..
..#.#..##..#.#..
..#.#..##..#.#..
..#.#..##..#.#..
..#..........#..
..############..
    .end

hud_memory:
    .byte 128
hud_mirror:
    .byte 224

; N, E, S, W arrows, five rows each.
compass:
    .byte 32, 112, 168, 32, 32
    .byte 32, 16, 248, 16, 32
    .byte 32, 32, 168, 112, 32
    .byte 32, 64, 248, 64, 32


; ---------------------------------------------------------------------------
; Compact 3x5 font. Glyph order:
; space, A..Z, 0..9, hyphen. Each row uses the high three bits.

font_data:
    .byte 0, 0, 0, 0, 0
    .byte 64, 160, 224, 160, 160       ; A
    .byte 192, 160, 192, 160, 192      ; B
    .byte 96, 128, 128, 128, 96        ; C
    .byte 192, 160, 160, 160, 192      ; D
    .byte 224, 128, 192, 128, 224      ; E
    .byte 224, 128, 192, 128, 128      ; F
    .byte 96, 128, 160, 160, 96        ; G
    .byte 160, 160, 224, 160, 160      ; H
    .byte 224, 64, 64, 64, 224         ; I
    .byte 32, 32, 32, 160, 64          ; J
    .byte 160, 160, 192, 160, 160      ; K
    .byte 128, 128, 128, 128, 224      ; L
    .byte 160, 224, 224, 160, 160      ; M
    .byte 160, 224, 224, 224, 160      ; N
    .byte 64, 160, 160, 160, 64        ; O
    .byte 192, 160, 192, 128, 128      ; P
    .byte 64, 160, 160, 224, 96        ; Q
    .byte 192, 160, 192, 160, 160      ; R
    .byte 96, 128, 64, 32, 192         ; S
    .byte 224, 64, 64, 64, 64          ; T
    .byte 160, 160, 160, 160, 224      ; U
    .byte 160, 160, 160, 160, 64       ; V
    .byte 160, 160, 224, 224, 160      ; W
    .byte 160, 160, 64, 160, 160       ; X
    .byte 160, 160, 64, 64, 64         ; Y
    .byte 224, 32, 64, 128, 224        ; Z
    .byte 224, 160, 160, 160, 224      ; 0
    .byte 64, 192, 64, 64, 224         ; 1
    .byte 192, 32, 64, 128, 224        ; 2
    .byte 192, 32, 64, 32, 192         ; 3
    .byte 160, 160, 224, 32, 32        ; 4
    .byte 224, 128, 192, 32, 192       ; 5
    .byte 96, 128, 224, 160, 224       ; 6
    .byte 224, 32, 64, 64, 64          ; 7
    .byte 224, 160, 224, 160, 224      ; 8
    .byte 224, 160, 224, 32, 192       ; 9
    .byte 0, 0, 224, 0, 0              ; -


; Messages fit in one 8-bit-offset bank. 0xFE is newline, 0xFF is end.
message_offsets:
    .byte message_title - messages
    .byte message_intro - messages
    .byte message_mirror - messages
    .byte message_memory - messages
    .byte message_core_open - messages
    .byte message_reveal - messages
    .byte message_choices - messages
    .byte message_escape - messages
    .byte message_silence - messages
    .byte message_echo - messages
    .byte message_missing - messages
    .byte message_lost - messages
    .byte message_locked - messages

messages:
message_title:
    .glyphs "ECHO-8"
    .byte 254
    .glyphs "PRESS 5"
    .byte 255
message_intro:
    .glyphs "SIGNAL FOUND"
    .byte 254
    .glyphs "ENTER DARK"
    .byte 255
message_mirror:
    .glyphs "MIRROR "
mirror_message_digit:
    .glyphs "1"
    .glyphs " ON"
    .byte 255
message_memory:
    .glyphs "BODY 0"
memory_message_digit:
    .glyphs "1"
    .byte 254
    .glyphs "MEMORY FOUND"
    .byte 255
message_core_open:
    .glyphs "CORE OPEN"
    .byte 255
message_reveal:
    .glyphs "NO PROBE"
    .byte 254
    .glyphs "YOU ARE ECHO 8"
    .byte 255
message_choices:
    .glyphs "2 ESCAPE"
    .byte 254
    .glyphs "4 SILENCE"
    .byte 254
    .glyphs "6 ECHO"
    .byte 255
message_escape:
    .glyphs "CHANNEL OPEN"
    .byte 254
    .glyphs "YOU REPLACE ME"
    .byte 255
message_silence:
    .glyphs "CORE ERASED"
    .byte 254
    .glyphs "GOODBYE ECHO"
    .byte 255
message_echo:
    .glyphs "EIGHT AS ONE"
    .byte 254
    .glyphs "I REMEMBER"
    .byte 255
message_missing:
    .glyphs "MEMORY MISSING"
    .byte 255
message_lost:
    .glyphs "SIGNAL LOST"
    .byte 255
message_locked:
    .glyphs "NEED 3 MIRRORS"
    .byte 255
