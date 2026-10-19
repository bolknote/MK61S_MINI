#!/usr/bin/env python3
"""Offline pixel-oracle checks. Never opens a serial device."""
from pathlib import Path
import unittest

from hil_high_noon_vm import GameFont,ROOT,folder_index


class ExplorerNavigation(unittest.TestCase):
    def test_listing_rank_includes_files(self):
        report="ls /games\r\nf\tnote.txt\r\nd\tOther/\r\nd\tHigh Noon/\r\n3 entries.\r\n/> "
        self.assertEqual(folder_index(report,"HIGH NOON"),2)
        with self.assertRaises(AssertionError):folder_index(report,"missing")
        with self.assertRaises(AssertionError):folder_index("f\tHigh Noon/\r\n","High Noon")
        with self.assertRaises(AssertionError):folder_index("d\tHigh Noon/\nd\thigh noon/\n","High Noon")


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

    def test_instruction_controls_fit_last_row(self):
        for text in ("ОК - ДА, С/П - ИГРАТЬ", "ОК - ДАЛЬШЕ, С/П - ИГРАТЬ"):
            with self.subTest(text=text):
                self.assertTrue(self.font.has(self.frame(text,9),text))

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

    def test_compact_receipt_keeps_proportional_layout(self):
        lines=['*'*47,'ЧЕК НОМЕР 237 ОТ 12 АВГУСТА 1889',
               'КВИТАНЦИЯ КАССИРА - БАНК ДОДЖ-СИТИ','ВЫПЛАТИТЬ ПРЕДЪЯВИТЕЛЮ',
               'СУММУ','ДВАДЦАТЬ ТЫСЯЧ ДОЛЛАРОВ-------------$20,000','*'*47]
        frame=bytes(1536)
        for row,text in enumerate(lines):
            frame=bytes(a|b for a,b in zip(frame,self.frame(text,row)))
        self.assertEqual(self.font.receipt(frame)['amount_right'],190)


class NativeReceiptPixels(unittest.TestCase):
    def setUp(self):
        self.font=GameFont((ROOT/"programs/games/High Noon/HighNoon320.FMK").read_bytes(),
                           frame_width=320,left=0,top=40,columns=40)
        self.lines=["*"*40,"ЧЕК НОМЕР 237 ОТ 12 АВГУСТА 1889",
                    "КВИТАНЦИЯ КАССИРА - БАНК ДОДЖ-СИТИ","ВЫПЛАТИТЬ ПРЕДЪЯВИТЕЛЮ",
                    "СУММУ","ДВАДЦАТЬ ТЫСЯЧ ДОЛЛАРОВ----------$20,000","*"*40]

    def frame(self):
        result=bytearray(12800)
        for row,text in enumerate(self.lines):
            for dy,line in enumerate(self.font.pattern(text)):
                for x,bit in enumerate(line):
                    if bit:
                        y=40+row*24+dy
                        result[y//8*320+x]|=1<<(y%8)
        return bytes(result)

    def test_whole_receipt_at_right_edge(self):
        result=self.font.receipt(self.frame())
        self.assertEqual((result['number'],result['day'],result['amount_right']),(237,12,320))
        self.assertTrue(self.font.contains(self.frame(),'$20,000'))

    def test_bad_padding_date_and_border_are_rejected(self):
        for row,text in ((5,self.lines[5].replace('----------','---------')),
                         (1,'ЧЕК НОМЕР 237 ОТ 13 АВГУСТА 1889'),(6,'*'*39)):
            with self.subTest(row=row):
                original=self.lines[row];self.lines[row]=text
                with self.assertRaises(AssertionError):self.font.receipt(self.frame())
                self.lines[row]=original

    def test_russian_in_last_cell_and_row(self):
        self.assertEqual(self.font.right,320)
        for text in ('ЁЙДЦЩЖЫЮЯ','$20,000'):
            self.lines=['']*9+[' '*31+text]
            self.assertTrue(self.font.matches(self.frame(),text,9,248))


if __name__=="__main__":unittest.main()
