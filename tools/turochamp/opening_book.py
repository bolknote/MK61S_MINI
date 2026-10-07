"""Small hand-curated opening tree; only numeric DATA ships to the device."""
from __future__ import annotations

# Three moves per side. These are chess move facts, not an imported database.
OPENINGS = {
    "Italian": "e2e4 e7e5 g1f3 b8c6 f1c4 f8c5",
    "Ruy Lopez": "e2e4 e7e5 g1f3 b8c6 f1b5 a7a6",
    "Scotch": "e2e4 e7e5 g1f3 b8c6 d2d4 e5d4",
    "Open Sicilian": "e2e4 c7c5 g1f3 d7d6 d2d4 c5d4",
    "Closed Sicilian": "e2e4 c7c5 b1c3 b8c6 g2g3 g7g6",
    "French": "e2e4 e7e6 d2d4 d7d5 b1c3 g8f6",
    "Caro-Kann": "e2e4 c7c6 d2d4 d7d5 b1c3 d5e4",
    "Scandinavian": "e2e4 d7d5 e4d5 d8d5 b1c3 d5a5",
    "Queen's Gambit Declined": "d2d4 d7d5 c2c4 e7e6 b1c3 g8f6",
    "Slav": "d2d4 d7d5 c2c4 c7c6 g1f3 g8f6",
    "Nimzo-Indian": "d2d4 g8f6 c2c4 e7e6 b1c3 f8b4",
    "King's Indian": "d2d4 g8f6 c2c4 g7g6 b1c3 f8g7",
    "English reversed Sicilian": "c2c4 e7e5 b1c3 g8f6 g2g3 d7d5",
    "English Indian": "c2c4 g8f6 b1c3 e7e5 g2g3 d7d5",
    "Reti": "g1f3 d7d5 g2g3 g8f6 f1g2 g7g6",
    "Reti to Queen's Gambit": "g1f3 d7d5 d2d4 g8f6 c2c4 e7e6",
    "King's Indian Attack": "g1f3 g8f6 g2g3 d7d5 f1g2 c7c5",
}


def packed_move(uci: str) -> int:
    if len(uci) != 4:
        raise ValueError(f'opening move must have four coordinates: {uci}')
    squares = []
    for offset in (0, 2):
        file, rank = uci[offset:offset+2]
        if file not in 'abcdefgh' or rank not in '12345678':
            raise ValueError(f'invalid opening coordinates: {uci}')
        squares.append(ord(file)-ord('a')+8*(int(rank)-1))
    return squares[0]+64*squares[1]


def records() -> list[tuple[int, int, int]]:
    nodes = {(): 1}
    edges = {}
    for line in OPENINGS.values():
        prefix = ()
        moves = line.split()
        if len(moves) != 6:
            raise ValueError('opening must contain three moves per side')
        for move in moves:
            following = prefix+(move,)
            if following not in nodes:
                nodes[following] = len(nodes)+1
                edges[(nodes[prefix],packed_move(move))] = nodes[following]
            prefix = following
    return [(parent,move,child) for (parent,move),child in sorted(edges.items())]


def data_statements() -> list[str]:
    rows = records()+[(0,0,0)]
    return ['DATA '+','.join(str(value) for row in rows[i:i+12] for value in row)
            for i in range(0,len(rows),12)]
