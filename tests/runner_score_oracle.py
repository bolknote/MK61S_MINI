"""Verify Runner's score overlay from a complete UC1609 framebuffer."""
import hashlib
import time

from runner_frame_player import screen
from runner_screen_oracle import cell_signature, indicator


def expected_score(level, collected):
    assert type(level) is int and 1 <= level <= 3
    assert type(collected) is int and 0 <= collected <= 7 * 36 and collected % 36 == 0
    remaining = 3 - (collected // 36).bit_count()
    text = f'L{level}  GOLd {remaining}'
    return text, list(screen(text))


def matches_score(frame, level, collected):
    if not isinstance(frame, (bytes, bytearray)) or len(frame) != 1536:
        return False
    _, masks = expected_score(level, collected)
    wanted = indicator(masks)
    return all(cell_signature(frame, cell) == cell_signature(wanted, cell)
               for cell in range(12))


def wait_score_frame(port, first_frame_index, level, collected, timeout=3):
    """Accept only complete frames received from the key gesture onward."""
    assert type(first_frame_index) is int and 0 <= first_frame_index <= len(port.frames)
    deadline = time.monotonic() + timeout
    index = first_frame_index
    while time.monotonic() < deadline:
        for position in range(index, len(port.frames)):
            frame = bytes(port.frames[position])
            if matches_score(frame, level, collected):
                text, masks = expected_score(level, collected)
                proof = dict(level=level, collected=collected, expected_text=text,
                             expected_masks=masks, first_frame_index=first_frame_index,
                             observed_frame_index=position, raw_frame_hex=frame.hex(),
                             frame_sha256=hashlib.sha256(frame).hexdigest())
                return frame, proof
        index = len(port.frames)
        port.pump(.02)
    raise AssertionError(('actual score frame not received', level, collected, first_frame_index))


def score_evidence_valid(case, level=1, collected=36):
    try:
        proof = case['score']
        frame = bytes.fromhex(proof['raw_frame_hex'])
        text, masks = expected_score(level, collected)
        return (proof['level'] == level and proof['collected'] == collected and
                type(proof['first_frame_index']) is int and proof['first_frame_index'] >= 0 and
                type(proof['observed_frame_index']) is int and
                proof['observed_frame_index'] >= proof['first_frame_index'] and
                proof['expected_text'] == text and proof['expected_masks'] == masks and
                proof['frame_sha256'] == hashlib.sha256(frame).hexdigest() and
                matches_score(frame, level, collected))
    except (KeyError, TypeError, ValueError, AssertionError):
        return False
