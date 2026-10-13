import unittest
from check_foreground_stack_elf import check

class ForegroundStackTest(unittest.TestCase):
    def image(self, allocation='sub.w sp, sp, #564'):
        return ('08010000 <main>:\n'
                ' 8010000: b580 push {r7, lr}\n'
                ' 8010002: b091 sub sp, #68\n'
                ' 8010004: f7ff bl 8020000 <setup>\n'
                '08020000 <class_terminal::execute(bool, bool)>:\n'
                ' 8020000: e92d stmdb sp!, {r4-r11, lr}\n'
                ' 8020004: ed2d vpush {d8}\n'
                f' 8020008: f5ad {allocation}\n'
                ' 802000c: f7ff bl 8030000 <handler>\n')

    def test_bounded_frames(self):
        self.assertEqual(check(self.image()), {'main':76, 'terminal dispatch':608})

    def test_rejects_lto_merged_scratch(self):
        with self.assertRaisesRegex(ValueError, 'terminal dispatch retains'):
            check(self.image('subw sp, sp, #1924'))

    def test_unknown_allocations_and_missing_entry(self):
        with self.assertRaises(ValueError):
            check(self.image('sub sp, sp, r3'))
        with self.assertRaisesRegex(ValueError, 'missing main'):
            check(self.image().split('08020000')[1])

if __name__ == '__main__':unittest.main()
