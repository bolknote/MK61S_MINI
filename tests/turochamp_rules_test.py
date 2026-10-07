#!/usr/bin/env python3
"""Independent chess oracle for the BASIC engine (pip install chess==1.11.2)."""
from __future__ import annotations
import argparse
import random
import selectors
import subprocess
from pathlib import Path
import chess

ROOT=Path(__file__).resolve().parents[1]

class Basic:
    def __init__(self,runner:Path):
        self.p=subprocess.Popen([str(runner),str(ROOT/'programs/games/Turochamp')],
                                stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,text=True,bufsize=1)
        self.s=selectors.DefaultSelector();self.s.register(self.p.stdout,selectors.EVENT_READ)
    def ask(self,line:str,timeout:float=40):
        self.p.stdin.write(line+'\n');self.p.stdin.flush()
        if not self.s.select(timeout):raise AssertionError('BASIC timeout: '+line)
        result=self.p.stdout.readline()
        if not result:
            raise AssertionError('BASIC failed: '+line+' '+self.p.stderr.read())
        return result.strip()
    def close(self):
        if self.p.poll() is None:self.p.terminate()
        self.p.wait();self.s.close()

POSITIONS=(
    (chess.STARTING_FEN,(20,400,8902)),
    ('r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1',(48,2039)),
    ('8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1',(14,191)),
    ('r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1',(6,264)),
    ('rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8',(44,1486)),
    ('r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10',(46,2079)),
    ('4k3/P7/8/8/8/8/7p/4K3 w - - 0 1',()),
    ('4k3/8/8/4KPpr/8/8/8/8 w - g6 0 1',()),
    ('4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1',()),
    ('r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 9 20',()),
)

def compare(b:Basic,board:chess.Board):
    expected={m.uci() for m in board.legal_moves}
    actual=set(b.ask('moves').split())
    assert actual==expected,(board.fen(),sorted(actual-expected),sorted(expected-actual))
    captures={m.uci() for m in board.legal_moves if board.is_capture(m) or m.promotion}
    assert set(b.ask('moves 4').split())==captures,board.fen()
    assert set(b.ask('moves 5').split())==expected-captures,board.fen()
    assert b.ask('position')==board.fen(en_passant='fen'),board.fen()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runner',type=Path,default=Path('/private/tmp/mk61-turochamp-runner'))
    ap.add_argument('--games',type=int,default=4)
    args=ap.parse_args();b=Basic(args.runner)
    try:
        for fen,counts in POSITIONS:
            board=chess.Board(fen);b.ask('fen '+fen);compare(b,board)
            for depth,count in enumerate(counts,1):
                actual=int(b.ask(f'perft {depth}'));assert actual==count,(fen,depth,actual,count)
            for move in list(board.legal_moves):
                b.ask('fen '+fen)
                got=b.ask('play '+move.uci());board.push(move)
                assert got==board.fen(en_passant='fen'),(fen,move,got,board.fen())
                board.pop();assert b.ask('undo')==fen,(fen,move)
        rng=random.Random(1948)
        for game in range(args.games):
            board=chess.Board();b.ask('fen '+board.fen())
            for ply in range(90):
                compare(b,board)
                moves=list(board.legal_moves)
                if not moves:break
                move=rng.choice(moves);got=b.ask('play '+move.uci());board.push(move)
                assert got==board.fen(en_passant='fen'),(game,ply,move,got,board.fen())
        b.ask('fen '+chess.STARTING_FEN)
        for count in range(1,5):
            for move in ('g1f3','g8f6','f3g1','f6g8'):b.ask('play '+move)
            before=b.ask('position');assert int(b.ask('repeat'))==count+1
            assert b.ask('position')==before
        print('Turochamp BASIC: legal moves, perft, all promotions, castling, en passant, undo and exact repetition PASS')
    finally:b.close()

if __name__=='__main__':main()
