"""Wire layout shared by generated BASIC parts and their host tests.

All chess logic runs in the emitted TinyBASIC. Python only assembles labels,
array aliases and the M61 call/return dispatcher.
"""

FIELDS = dict(zip(
    "SIDE RIGHTS EP HALF FULL WK BK LASTCAP CW CB HCOUNT HEP MODE CUR SEL PROMO "
    "RESULT CHECK CLAIM MOVE LAST COUNT REPS CP PHASE SP NODES DFS ROOT BEST "
    "ROOTPOS ROOTVAL ALPHA LFRAME GLSTATE GLMOVE GLSIDE GLMODE GLPIECE GLTYPE "
    "APMOVE APFRAME APSIDE AQ AS AT AN STAT MATW MATB PE PCS REPDEP REPRESULT "
    "ED EF EC ES ECHECK ETHREAT ROOTC LEVEL QLIMIT SIM".split(),
    range(120, 184)))
FIELDS.update(HIST=184, STACK=222, RETURNS=278, GEN_CURSOR=288,
              E_CURSOR=289, E_MOVE=290, E_UNDO=291, G_UNDO=293,
              STATUS_CURSOR=295, RP_META=296, RP_KEY=301, RP_HCUR=306,
              RP_STATE=307, RP_DEPTH=308, RP_COUNT=309, RP_BRANCH=310,
              UI_ITER=311, UI_ACTION=312, UI_PHASE=313, UI_KEY=314,
              UI_TEST=315, UI_MESSAGE=316, UI_FROM=317, UI_TO=318,
              UI_VIEW=319, UI_FLAGS=320, ROOTCURSOR=321, ROOTEVAL=322,
              ROOTMAT=323, ROOTTMP=324, SEARCH_CUR=326, RETVAL=327,
              RP_BACK=328, RP_FORWARD=329, H_MOVE=330, H_SLOT=331,
              H_KEEP=332, DRAW_REASON=333, GAIN=334, TMP=335,
              DIRN=336, DIRS=344)

# Preserve the remaining M61 IDs when removing or merging parts.
MODULES = {
    "init": 1, "game": 2, "board": 3, "pseudo": 4, "legal": 5,
    "make": 7, "unmake": 8, "status": 9, "repeat": 10, "eval": 11,
    "search": 12, "turn": 13, "history": 14, "menu": 15, "promote": 16,
    "claim": 17, "castle": 20, "mobility": 21, "threat": 22, "ep": 23,
    "rkey": 24, "rstep": 25, "node": 26, "claims": 28, "help": 29,
}
LOCAL_ONLY = {"attack", "pawns"}

SOURCE_BUDGET = 2800  # M8 bytes, including conservative CRLF overhead.
MAX_ARRAY_INDEX = 351
FRAME_SIZE = 7
MAX_SEARCH_PLIES = 8

assert len(FIELDS) == len(set(FIELDS))
assert FIELDS["SIM"] == 183
assert FIELDS["HIST"] + 38 == FIELDS["STACK"]
assert FIELDS["STACK"] + FRAME_SIZE * MAX_SEARCH_PLIES == FIELDS["RETURNS"]
