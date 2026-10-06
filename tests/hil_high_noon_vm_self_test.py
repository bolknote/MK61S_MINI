#!/usr/bin/env python3
"""Offline pixel-oracle checks. Never opens a serial device."""
from pathlib import Path
import unittest

from hil_high_noon_vm import GameFont,ROOT


class GamePixels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font=GameFont((ROOT/"programs/games/High Noon/HighNoon.FMK").read_bytes())

    def frame(self,text,row=0,x=2):
        result=bytearray(1536)
        for dy,line in enumerate(self.font.pattern(text)):
            for dx,bit in enumerate(line):
                if bit:
                    y=2+row*6+dy
                    result[y//8*192+x+dx]|=1<<(y%8)
        return bytes(result)

    def test_known_dollar_bitmap(self):
        self.assertEqual(self.font.glyphs[ord("$")],
                         (5,6,(0b01110,0b10100,0b01110,0b00101,0b01110)))

    def test_number_in_every_row(self):
        for row in range(10):
            with self.subTest(row=row):
                frame=self.frame("МЕЖДУ ВАМИ 90 ШАГОВ.",row)
                self.assertTrue(self.font.has(frame,"МЕЖДУ ВАМИ "))
                self.assertEqual(self.font.number_after(frame,"МЕЖДУ ВАМИ "),90)
                self.assertFalse(self.font.has(frame,"ВАША СТРАТЕГИЯ?"))

    def test_receipt_suffix_and_bounds(self):
        frame=self.frame("$20,000",5,150)
        self.assertTrue(self.font.contains(frame,"$20,000"))
        self.assertFalse(self.font.has(frame,"$20,000"))
        self.assertFalse(self.font.has(bytes(1536),"$20,000"))
        self.assertFalse(self.font.has(bytes(1536),"*"*48))

    def test_russian_not_latin_fallback(self):
        with self.assertRaises(KeyError):self.font.pattern("DFU")


if __name__=="__main__":unittest.main()
