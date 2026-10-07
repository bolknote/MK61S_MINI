#!/usr/bin/env python3
"""Adjudication, historic evaluation, search and actual keyboard-driven BASIC."""
from __future__ import annotations
import argparse
import math
import random
import sys
from pathlib import Path
import chess
from turochamp_rules_test import Basic, ROOT

sys.path.insert(0, str(ROOT/'tools/turochamp'))
from layout import FIELDS, MODULES


def setv(b, **values):
    for name, value in values.items():
        b.ask(f'set {FIELDS[name]} {value}')


def getv(b, name):
    return int(float(b.ask(f'get {FIELDS[name]}')))


def status(b):
    return tuple(map(int, b.ask('status').split()))


def positional(board, side):
    """Independent bitboard implementation of the seven published criteria."""
    def mobility(square, queen=False):
        position = board.copy(stack=False)
        if queen:
            position.set_piece_at(square, chess.Piece(chess.QUEEN, side))
        count = sum(1 if not position.piece_at(t) else 2
                    for t in position.attacks(square)
                    if not position.piece_at(t) or position.color_at(t) != side)
        return math.floor(10*math.sqrt(count)+.5)

    value = 0
    for square, piece in board.piece_map().items():
        if piece.color != side:
            continue
        defenders = board.attackers(side, square)
        if piece.piece_type == chess.PAWN:
            advanced = chess.square_rank(square)-1 if side else 6-chess.square_rank(square)
            value += 2*advanced
            if any(board.piece_type_at(t) != chess.PAWN for t in defenders):
                value += 3
            continue
        value += mobility(square)
        if piece.piece_type in (chess.ROOK, chess.BISHOP, chess.KNIGHT):
            value += 10 if len(defenders) == 1 else 15 if len(defenders) > 1 else 0
        if piece.piece_type == chess.KING:
            value -= mobility(square, queen=True)
    if board.is_attacked_by(side, board.king(not side)):
        value += 5
    own = board.copy(stack=False)
    if own.turn != side:
        own.ep_square = None
    own.turn = side
    threat, castle = False, False
    for move in list(own.legal_moves):
        # An imaginary extra turn must still never capture the other king.
        if own.piece_type_at(move.to_square) == chess.KING:
            continue
        castle |= own.is_castling(move)
        own.push(move)
        threat |= own.is_checkmate()
        own.pop()
    return value + 10*threat, int(threat)+2*int(castle)


def adjudication(b):
    positions = (
        ('7k/6Q1/5K2/8/8/8/8/8 b - - 150 80', 1),
        ('8/8/8/8/8/5k2/6q1/7K w - - 150 80', 2),
        ('7k/5K2/6Q1/8/8/8/8/8 b - - 0 1', 3),
        ('4k3/8/8/8/8/8/8/4K3 w - - 0 1', 4),
        ('4k3/8/8/8/8/8/8/2B1K3 w - - 0 1', 4),
        ('4k3/8/8/8/8/8/8/2N1K3 w - - 0 1', 4),
        ('4kb2/8/8/8/8/8/8/2B1K3 w - - 0 1', 4),
        ('4k3/8/8/8/8/8/8/1NN1K3 w - - 0 1', 0),
        ('2b1k3/8/8/8/8/8/8/2B1K3 w - - 0 1', 0),
        ('4k3/8/8/8/8/8/8/R3K3 w - - 149 75', 0),
        ('4k3/8/8/8/8/8/8/R3K3 w - - 150 76', 6),
    )
    for fen, result in positions:
        b.ask('fen '+fen)
        assert status(b)[0] == result, (fen, status(b))
        assert b.ask('position') == fen
    # The complete reversible window must fit at the automatic 75-move limit.
    board = chess.Board('4k1n1/8/8/8/8/8/8/4K1N1 w - - 0 1')
    b.ask('fen '+board.fen())
    for i in range(150):
        move = ('g1f3', 'g8f6', 'f3g1', 'f6g8')[i % 4]
        board.push_uci(move)
        assert b.ask('play '+move) == board.fen(en_passant='fen')
    assert status(b)[0] == 6
    assert int(b.ask('repeat')) == 38
    assert b.ask('position') == board.fen(en_passant='fen')
    for count in (99, 100):
        fen = f'4k3/8/8/8/8/8/8/R3K3 w - - {count} 50'
        b.ask('fen '+fen)
        assert status(b)[2] == (0 if count == 99 else 2)
        claim, move = b.ask('claims').split()
        assert claim == '2' and (move != '-' if count == 99 else move == '-')
        assert b.ask('position') == fen
    # A selected pawn move cannot be announced to claim the fifty-move rule.
    b.ask('fen 4k3/8/8/8/8/8/P7/R3K3 w - - 99 50')
    setv(b, SEL=31, CUR=41)
    assert b.ask('claims') == '0 -'
    # Repetition uses legal EP rights, not just the FEN target field.
    for fen, cycle, expected in (
        ('4k3/8/8/4KPpr/8/8/8/8 w - g6 0 1',
         ('e5d4', 'e8d8', 'd4e5', 'd8e8'), 2),
        ('4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1',
         ('e1d1', 'e8d8', 'd1e1', 'd8e8'), 1),
    ):
        b.ask('fen '+fen)
        board = chess.Board(fen)
        for move in cycle:
            board.push_uci(move)
            b.ask('play '+move)
        assert int(b.ask('repeat')) == expected
        assert b.ask('position') == board.fen(en_passant='fen')
    b.ask('fen '+chess.STARTING_FEN)
    for i in range(7):
        b.ask('play '+('g1f3', 'g8f6', 'f3g1', 'f6g8')[i % 4])
    before = b.ask('position')
    assert b.ask('claims') == '1 f6g8'
    assert b.ask('position') == before
    b.ask('play f6g8')
    assert status(b)[2:4] == (1, 3)
    for _ in range(2):
        for move in ('g1f3', 'g8f6', 'f3g1', 'f6g8'):
            b.ask('play '+move)
    assert status(b)[0] == 5


def evaluation(b):
    rng = random.Random(1952)
    boards = [chess.Board(), chess.Board('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1'),
              chess.Board('7k/8/5KQ1/8/8/8/8/8 w - - 0 1')]
    board = chess.Board()
    for i in range(50):
        board.push(rng.choice(list(board.legal_moves)))
        if i % 5 == 0:
            boards.append(board.copy())
    for board in boards:
        fen = board.fen(en_passant='fen')
        b.ask('fen '+fen)
        for side in (chess.WHITE, chess.BLACK):
            ppv, flags = b.ask('eval '+('1' if side else '-1')).split()
            expected = positional(board, side)
            assert (round(float(ppv)*10), int(flags)) == expected, (fen, side, ppv, flags, expected)
            assert b.ask('position') == fen


def search(b):
    b.ask('fen '+chess.STARTING_FEN)
    assert b.ask('best').split()[0] == 'e2e3'
    for fen in ('7k/8/5KQ1/8/8/8/8/8 w - - 0 1',
                '8/8/8/8/8/5kq1/8/7K b - - 0 1',
                '4k3/P7/8/8/8/8/7p/4K3 w - - 0 1',
                'r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1'):
        board = chess.Board(fen)
        b.ask('fen '+fen)
        move = chess.Move.from_uci(b.ask('best').split()[0])
        assert move in board.legal_moves, (fen, move)
        if any(board.gives_check(m) and terminal_mate(board, m) for m in board.legal_moves):
            assert terminal_mate(board, move), (fen, move)
        assert b.ask('position') == fen
    for fen in ('7k/8/5KQ1/8/8/8/8/8 w - - 0 1',
                '4k3/P7/8/8/8/8/7p/4K3 w - - 0 1',
                '4k3/8/8/8/8/8/p7/1R2K3 w - - 0 1'):
        board = chess.Board(fen)
        b.ask('fen '+fen)
        got = b.ask('best').split()
        expected = reference_search(board)
        assert (got[0],int(got[1])) == expected, (fen,got,expected)


def reference_search(board):
    """Exhaustive reference; no BASIC mailbox, packed stack or alpha-beta."""
    weights = (0,2,6,7,10,20,0)
    def material():
        return sum(weights[p.piece_type]*(1 if p.color == board.turn else -1)
                   for p in board.piece_map().values())
    def node(depth, previous_check, captured_square):
        result = board.outcome()
        if result:
            return 0 if result.winner is None else -2000+depth
        if depth == 8:
            return material()
        selective = depth >= 2 and not board.is_check()
        if selective and not (previous_check or
                              captured_square is not None and board.attackers(board.turn,captured_square)):
            return material()
        best = material() if selective else -100000
        checked = board.is_check()
        for move in list(board.legal_moves):
            capture = board.is_capture(move)
            if selective and not (capture or move.promotion):
                continue
            board.push(move)
            value = -node(depth+1,checked,move.to_square if capture else None)
            board.pop()
            best = max(best,value)
        return best
    side = board.turn
    base = positional(board,side)[0]
    rights = board.has_castling_rights(side)
    candidates = []
    for move in list(board.legal_moves):
        castle, checked, capture = board.is_castling(move), board.is_check(), board.is_capture(move)
        board.push(move)
        value, flags = positional(board,side)
        value += 10*(castle+bool(flags & 2)+(rights and board.has_castling_rights(side)))
        value -= base
        value += 5000*(-node(1,checked,move.to_square if capture else None))
        board.pop()
        key = (chess.square_file(move.from_square),chess.square_rank(move.from_square),
               chess.square_file(move.to_square),chess.square_rank(move.to_square))
        candidates.append((-value,key,move.uci()))
    candidate = min(candidates)
    return candidate[2], -candidate[0]


def terminal_mate(board, move):
    board.push(move)
    result = board.is_checkmate()
    board.pop()
    return result


def keyboard(b):
    assert b.ask('ui 19') == chess.STARTING_FEN
    assert b.ask('ui 19 19 17 17 19') == 'rnbqkbnr/pppp1ppp/4p3/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2'
    assert b.ask('ui 16 19') == 'rnbqkbnr/pppppppp/8/8/8/4P3/PPPP1PPP/RNBQKBNR b KQkq - 0 1'
    assert b.ask('ui 16 16 19 19 17 17 19') == 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1'
    # Cancel, illegal pawn movement, help return, resignation, agreed draw.
    for keys in ('19 19 22', '19 19 17 17 17 19', '19 25 19 19'):
        assert b.ask('ui '+keys) == chess.STARTING_FEN
    b.ask('ui 19 21 16 16 16 19')
    assert getv(b, 'RESULT') == 2
    b.ask('ui 16 16 19 21 16 16 19 19')
    assert getv(b, 'RESULT') == 9
    # A new game returns to side selection with all board/history data reset.
    assert b.ask('ui 16 16 19 19 17 17 19 21 15 19') == chess.STARTING_FEN
    assert getv(b, 'HCOUNT') == 0
    # All promotion choices are made through the shipping keyboard dialog.
    for key, piece in (('19','Q'), ('16 19','N'), ('16 16 19','B'), ('16 16 16 19','R'),
                       ('15 15 15 19','N')):
        b.ask('fen 4k3/P7/8/8/8/8/8/4K3 w - - 0 1')
        setv(b, SEL=81, CUR=91, UI_VIEW=1, MODE=0)
        assert b.ask(f'keys {MODULES["promote"]} '+key) == f'{piece}3k3/8/8/8/8/8/8/4K3 b - - 0 1'
    b.ask('fen 4k3/8/8/8/8/8/8/R3K3 w - - 99 50')
    setv(b, SEL=21, CUR=31, UI_VIEW=1, MODE=0)
    before = b.ask('position')
    b.ask(f'keys {MODULES["claim"]} 19')
    assert getv(b, 'RESULT') == 8 and b.ask('position') == before
    b.ask('fen 4k3/8/8/8/8/8/8/R3K3 w - - 99 50')
    setv(b, SEL=21, CUR=31, UI_VIEW=1, MODE=0)
    b.ask(f'keys {MODULES["claim"]} 22')
    assert getv(b, 'RESULT') == 0
    for fen, cursor, keys, uci in (
        ('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1',25,'19 16 16 19','e1g1'),
        ('4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1',65,'19 15 17 19','e5d6'),
        ('7k/8/5KQ1/8/8/8/8/8 w - - 0 1',77,'19 17 19','g6g7'),
        ('4k3/8/8/8/8/8/7p/4K3 b - - 0 1',38,'19 17 19 16 19','h2h1n'),
    ):
        b.ask('fen '+fen)
        board = chess.Board(fen)
        setv(b, CUR=cursor, MODE=0, UI_VIEW=1 if board.turn else -1)
        board.push_uci(uci)
        assert b.ask(f'keys {MODULES["game"]} '+keys) == board.fen(en_passant='fen')
        if board.is_checkmate():
            assert getv(b,'RESULT') == 1
    b.ask('fen 4k3/P7/8/8/8/8/8/4K3 w - - 0 1')
    setv(b, SEL=81, CUR=91, MODE=0, UI_VIEW=1)
    before = b.ask('position')
    assert b.ask(f'keys {MODULES["promote"]} 22') == before and getv(b,'SEL') == 0


def screen(b):
    from turochamp_package_self_test import decode_font
    font = decode_font((ROOT/'programs/games/Turochamp/Turochamp.FMK').read_bytes())
    seen = set()

    def check_cells(board):
        view, cursor, selected = (getv(b,x) for x in ('UI_VIEW','CUR','SEL'))
        cells = bytes.fromhex(b.ask('screen'))
        assert len(cells) == 26*9
        assert cells[1:9] == (b'abcdefgh' if view == 1 else b'hgfedcba')
        for y in range(8):
            rank = 8-y if view == 1 else y+1
            assert cells[26*(y+1)] == ord(str(rank))
            for x in range(1,9):
                file = x if view == 1 else 9-x
                square = chess.square(file-1,rank-1)
                piece = board.piece_at(square)
                value = 0 if not piece else piece.piece_type*(1 if piece.color else -1)
                mailbox = 10*(rank+1)+file
                index = 13*((file+rank+1)%2)+value+6
                expected = 0xe0+index if mailbox in (cursor,selected) else ord('A')+index
                actual = cells[26*(y+1)+x]
                assert actual == expected, (view, chess.square_name(square),actual,expected)
                assert actual in font
                seen.add(actual)

    for keys in ('19','16 19','16 16 19 19 17 17 19'):
        check_cells(chess.Board(b.ask('ui '+keys)))

    # A render-only fixture puts each piece/empty cell on both square colours.
    # Highlight each square in turn to cover all 52 glyphs in both orientations.
    board = chess.Board.empty()
    for i, value in enumerate(range(-6,7)):
        if value:
            for square in (2*i,2*i+1):
                board.set_piece_at(square, chess.Piece(abs(value), value > 0))
    for view in (1,-1):
        b.ask('fen '+board.fen())
        setv(b, UI_VIEW=view, UI_MESSAGE=0, CUR=0, SEL=0)
        for square in (None,*range(26)):
            cursor = 0 if square is None else 10*(chess.square_rank(square)+2)+chess.square_file(square)+1
            setv(b, CUR=cursor)
            b.ask(f'keys {MODULES["board"]}')
            check_cells(board)
    assert seen == set(range(ord('A'),ord('Z')+1)) | set(range(0xe0,0xfa))


def selfplay(b):
    board = chess.Board()
    b.ask('fen '+board.fen())
    for ply in range(1000):
        state = status(b)
        if state[0]:
            assert board.outcome() is not None, (board.fen(), state)
            print(f'Turochamp selfplay: {ply} plies, {board.outcome()}', flush=True)
            return
        try:
            move = b.ask('best', timeout=300).split()[0]
        except AssertionError as error:
            raise AssertionError(f'selfplay ply {ply}, {board.fen()}: {error}') from error
        if move == 'draw':
            assert board.can_claim_draw(), board.fen()
            print(f'Turochamp selfplay: {ply} plies, valid draw claim', flush=True)
            return
        m = chess.Move.from_uci(move)
        assert m in board.legal_moves, (board.fen(), move)
        board.push(m)
        assert b.ask('play '+move) == board.fen(en_passant='fen')
        if ply % 10 == 9:
            print(f'Turochamp selfplay: {ply+1} plies checked', flush=True)
    raise AssertionError('selfplay did not finish in the test time budget')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runner', type=Path, default=Path('/private/tmp/mk61-turochamp-runner'))
    ap.add_argument('--selfplay', action='store_true')
    args = ap.parse_args()
    b = Basic(args.runner)
    try:
        for test in (adjudication, evaluation, search, keyboard, screen):
            test(b)
            print(f'Turochamp BASIC: {test.__name__} PASS', flush=True)
        if args.selfplay:
            selfplay(b)
    finally:
        b.close()


if __name__ == '__main__':
    main()
