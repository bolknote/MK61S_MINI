"""HOST-only score regressions; no calculator, process or transport is opened."""
import copy
import hashlib
import unittest
from unittest.mock import patch

import runner_score_oracle as oracle
from runner_frame_player import screen
from runner_screen_oracle import indicator


class Clock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now


class Frames:
    def __init__(self, clock, initial, arrivals):
        self.clock = clock
        self.frames = list(initial)
        self.arrivals = list(arrivals)

    def pump(self, duration):
        self.clock.now += duration
        if self.arrivals:
            self.frames.append(self.arrivals.pop(0))


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.timer = patch.object(oracle, 'time', self.clock)
        self.timer.start()
        self.addCleanup(self.timer.stop)
        self.good = indicator(screen('L1  GOLd 2'))
        self.board = indicator([107] + [8] * 11)

    def wait(self, initial, arrivals):
        port = Frames(self.clock, initial, arrivals)
        return oracle.wait_score_frame(port, len(initial), 1, 36, timeout=.12)

    def proof(self):
        _, proof = self.wait([self.board], [self.good])
        return dict(score=proof)

    def test_remaining_gold_text(self):
        for level in (1, 2, 3):
            for collected, remaining in ((0, 3), (36, 2), (108, 1), (252, 0)):
                with self.subTest(level=level, collected=collected):
                    self.assertEqual(oracle.expected_score(level, collected)[0],
                                     f'L{level}  GOLd {remaining}')

    def test_fresh_exact_frame_has_portable_proof(self):
        frame, proof = self.wait([self.board], [self.board, self.good])
        self.assertEqual(frame, self.good)
        self.assertEqual(proof['observed_frame_index'], 2)
        self.assertEqual(bytes.fromhex(proof['raw_frame_hex']), frame)
        self.assertTrue(oracle.score_evidence_valid(dict(score=proof)))

    def test_suppressed_button_and_sprite_motion_fail(self):
        moved = indicator([8, 107] + [8] * 10)
        with self.assertRaises(AssertionError):
            self.wait([self.board], [self.board, moved, self.board])

    def test_stale_correct_score_fails(self):
        with self.assertRaises(AssertionError):
            self.wait([self.good], [self.board])

    def test_wrong_gold_and_level_fail(self):
        for text in ('L1  GOLd 3', 'L2  GOLd 2'):
            with self.subTest(text=text), self.assertRaises(AssertionError):
                self.clock.now = 0
                self.wait([self.board], [indicator(screen(text))])

    def test_all_twelve_cells_must_match(self):
        masks = list(screen('L1  GOLd 2'))
        masks[-1] = 107
        self.assertFalse(oracle.matches_score(indicator(masks), 1, 36))

    def test_unrelated_ui_pixels_are_allowed(self):
        frame = bytearray(self.good)
        frame[0] ^= 1
        self.assertTrue(oracle.matches_score(frame, 1, 36))

    def test_incomplete_or_non_frame_data_fail(self):
        for frame in (None, '', bytes(1535), bytes(1537)):
            with self.subTest(frame_type=type(frame)):
                self.assertFalse(oracle.matches_score(frame, 1, 36))

    def test_parent_rechecks_raw_bitmap_hash_and_freshness(self):
        good = self.proof()
        for mutation in ('bitmap', 'hash', 'stale', 'negative', 'text', 'masks',
                         'level', 'collected', 'hex', 'missing'):
            row = copy.deepcopy(good)
            p = row['score']
            if mutation == 'bitmap':
                p['raw_frame_hex'] = self.board.hex()
                p['frame_sha256'] = hashlib.sha256(self.board).hexdigest()
            elif mutation == 'hash':
                p['frame_sha256'] = '0' * 64
            elif mutation == 'stale':
                p['observed_frame_index'] = p['first_frame_index'] - 1
            elif mutation == 'negative':
                p['first_frame_index'] = -1
            elif mutation == 'text':
                p['expected_text'] = 'L1  GOLd 3'
            elif mutation == 'masks':
                p['expected_masks'][-1] = 107
            elif mutation == 'level':
                p['level'] = 2
            elif mutation == 'collected':
                p['collected'] = 0
            elif mutation == 'hex':
                p['raw_frame_hex'] = 'not hex'
            else:
                row = {}
            with self.subTest(mutation=mutation):
                self.assertFalse(oracle.score_evidence_valid(row))


if __name__ == '__main__':
    unittest.main()
