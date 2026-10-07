#!/usr/bin/env python3
"""Independent opening-table legality and shipping BASIC book integration."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import re
import sys
import chess
from turochamp_rules_test import Basic, ROOT
from turochamp_game_test import getv, setv

sys.path.insert(0,str(ROOT/'tools/turochamp'))
from layout import MODULES
from opening_book import OPENINGS


def read_table():
    # Read the emitted device DATA, independent of the assembler's tree packer.
    source = (ROOT/'programs/games/Turochamp/history.tbi').read_text()
    numbers = []
    for line in re.findall(r'^\d+ DATA (.*)$',source,re.M):
        numbers.extend(map(int,line.split(',')))
    assert len(numbers)%3 == 0 and numbers[-3:] == [0,0,0]
    rows = [tuple(numbers[i:i+3]) for i in range(0,len(numbers)-3,3)]
    children = defaultdict(dict)
    boards = {1:chess.Board()}
    for parent, packed, child in rows:
        assert parent in boards and child > parent and child not in boards
        move = chess.Move(packed%64,packed//64)
        assert move in boards[parent].legal_moves, (parent,move,boards[parent].fen())
        assert move.uci() not in children[parent]
        children[parent][move.uci()] = child
        following = boards[parent].copy()
        following.push(move)
        boards[child] = following
    assert set(children[1]) == {'e2e4','d2d4','c2c4','g1f3'}
    assert max(len(b.move_stack) for b in boards.values()) == 6
    leaves = set(boards)-set(children)
    endings = set()
    for line in OPENINGS.values():
        node = 1
        for move in line.split():
            node = children[node][move]
        assert node in leaves
        endings.add(node)
    assert leaves == endings and len(leaves) == len(OPENINGS)
    return children, boards


def selection(b,children,boards):
    for node,pool in children.items():
        board = boards[node]
        fen = board.fen(en_passant='fen')
        b.ask('fen '+fen)
        setv(b,BOOK_ENABLED=1,BOOK_NODE=node)
        seen = set()
        count = 64 if len(pool)>1 else 1
        for _ in range(count):
            move,parent,enabled = b.ask('book').split()
            assert move in pool and int(parent) == node and enabled == '1', (node,move,pool)
            assert getv(b,'BOOK_ACTION') == 0
            assert getv(b,'BOOK_NEXT') == pool[move]
            assert b.ask('position') == fen
            seen.add(move)
        assert seen == set(pool), (node,seen,pool)
    # Running the real BASIC initialization preserves the RNG between games.
    b.ask('fen '+chess.STARTING_FEN)
    counts = Counter()
    for _ in range(128):
        assert b.ask('new') == chess.STARTING_FEN
        counts[b.ask('book').split()[0]] += 1
    assert set(counts) == set(children[1]) and min(counts.values()) >= 12, counts
    print('Turochamp book: all DATA moves legal, every choice reachable, new-game variety PASS',flush=True)


def advancement(b,children):
    for line in OPENINGS.values():
        b.ask('fen '+chess.STARTING_FEN)
        board = chess.Board()
        node = 1
        for move in line.split():
            # Choosing must not advance the node; only an actual committed move does.
            picked = b.ask('book').split()[0]
            assert picked in children[node]
            node = children[node][move]
            board.push_uci(move)
            assert b.ask('play '+move) == board.fen(en_passant='fen')
            assert getv(b,'BOOK_NODE') == node
        assert b.ask('book').split()[0] == 'none'
        assert getv(b,'BOOK_NODE') == 0
    b.ask('fen '+chess.STARTING_FEN)
    b.ask('play e2e3')
    assert getv(b,'BOOK_NODE') == 0 and b.ask('book').split()[0] == 'none'
    before = b.ask('position')
    move = chess.Move.from_uci(b.ask('best').split()[0])
    assert move in chess.Board(before).legal_moves and getv(b,'NODES') > 0
    assert b.ask('position') == before
    # A stale node cannot make the book return a move for the wrong side.
    b.ask('fen '+chess.STARTING_FEN)
    setv(b,SIDE=-1,BOOK_NODE=1)
    before = b.ask('position')
    assert b.ask('book').split()[0] == 'none' and getv(b,'BOOK_NODE') == 0
    assert b.ask('position') == before
    b.ask('fen '+chess.STARTING_FEN)
    setv(b,BOOK_NODE=999)
    assert b.ask('book').split()[0] == 'none' and getv(b,'BOOK_NODE') == 0
    print('Turochamp book: all 17 complete lines, departure, end-of-book and legality guard PASS',flush=True)


def keyboard(b,children):
    board = chess.Board(b.ask('ui 16 19'))
    assert getv(b,'BOOK_ENABLED') == 1 and getv(b,'NODES') == 0
    assert board.turn == chess.BLACK
    expected = chess.Board()
    first = getv(b,'LAST')
    f,t = first%128,(first//128)%128
    first_uci = ''.join((chr(96+f%10),str(f//10-1),chr(96+t%10),str(t//10-1)))
    assert first_uci in children[1]
    expected.push_uci(first_uci)
    assert board.fen(en_passant='fen') == expected.fen(en_passant='fen')
    assert getv(b,'BOOK_NODE') == children[1][first_uci]

    board = chess.Board(b.ask('ui 19 19 17 17 19'))
    assert board.turn == chess.WHITE and getv(b,'NODES') == 0
    expected = chess.Board()
    expected.push_uci('e2e4')
    reply_node = children[1]['e2e4']
    matches = []
    for reply,child in children[reply_node].items():
        test = expected.copy();test.push_uci(reply)
        if test.fen(en_passant='fen') == board.fen(en_passant='fen'):
            matches.append(child)
    assert matches == [getv(b,'BOOK_NODE')]

    # Unknown e3 returns to the historical search and clears the book path.
    b.ask('ui 19 19 17 19')
    assert getv(b,'BOOK_NODE') == 0 and getv(b,'NODES') > 0
    # Book off gives exactly the historical e3, and survives a new game.
    assert b.ask('ui 16 16 16 16 19 16 16 19') == (
        'rnbqkbnr/pppppppp/8/8/8/4P3/PPPP1PPP/RNBQKBNR b KQkq - 0 1')
    assert getv(b,'BOOK_ENABLED') == 2
    assert b.ask('new') == chess.STARTING_FEN and getv(b,'BOOK_ENABLED') == 2
    # Enable again in the existing new-game menu and start as Black.
    b.ask(f'keys {MODULES["menu"]} 16 16 16 16 19 16 16 19')
    assert getv(b,'BOOK_ENABLED') == 1 and getv(b,'NODES') == 0
    print('Turochamp book: White/Black UI, on/off, remembered setting, fallback PASS',flush=True)


def selfplay(b):
    board = chess.Board()
    b.ask('fen '+board.fen())
    book_moves = 0
    for ply in range(1000):
        state = tuple(map(int,b.ask('status').split()))
        if state[0]:
            assert board.outcome() is not None and book_moves == 6, (board.fen(),state,book_moves)
            print(f'Turochamp book selfplay: {ply} plies, {book_moves} book moves, {board.outcome()}',flush=True)
            return
        choice = b.ask('book').split()[0] if getv(b,'BOOK_NODE') else 'none'
        if choice == 'none':
            choice = b.ask('best',timeout=300).split()[0]
        else:
            book_moves += 1
        if choice == 'draw':
            assert board.can_claim_draw() and book_moves == 6
            print(f'Turochamp book selfplay: {ply} plies, {book_moves} book moves, valid draw claim',flush=True)
            return
        move = chess.Move.from_uci(choice)
        assert move in board.legal_moves, (board.fen(),choice)
        board.push(move)
        assert b.ask('play '+choice) == board.fen(en_passant='fen')
        if ply%10 == 9:
            print(f'Turochamp book selfplay: {ply+1} plies checked',flush=True)
    raise AssertionError('book selfplay did not finish in the test time budget')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runner',type=Path,default=Path('/private/tmp/mk61-turo-book-runner'))
    ap.add_argument('--selfplay',action='store_true')
    args = ap.parse_args()
    children,boards = read_table()
    b = Basic(args.runner)
    try:
        selection(b,children,boards)
        advancement(b,children)
        keyboard(b,children)
        if args.selfplay:
            selfplay(b)
    finally:
        b.close()


if __name__ == '__main__':
    main()
