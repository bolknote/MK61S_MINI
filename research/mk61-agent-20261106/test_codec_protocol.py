import unittest
from byte_codec import huffman
from codec_common import Protocol


class ProtocolTests(unittest.TestCase):
    def setUp(self):self.p=Protocol('h32',huffman({96:10000,80:10000},32))

    def test_program_and_roundtrip(self):
        original='<calc>+ R0 R1</calc><write>60 61 10 50</write><run/>'
        encoded=self.p.encode_text(original)
        self.assertNotIn('60 61',encoded)
        self.assertEqual(self.p.decode_reply(encoded),(original,None))

    def test_feedback_fields_without_changing_numbers(self):
        text='Код — байты HEX.\nИсправь код: 60 61 10 50\nЭмулятор: TRACE 02:10 X=60; ожидалось X=10'
        out=self.p.encode_text(text)
        self.assertIn('H32',out)
        self.assertNotIn('02:10',out)
        self.assertIn('X=60; ожидалось X=10',out)

    def test_malformed_code_cannot_pass_as_hex(self):
        normalized,error=self.p.decode_reply('<write>60 61 10 50</write><run/>')
        self.assertIsNotNone(error)
        self.assertNotIn('<write>',normalized)
        word=next(x for x in self.p.codec.codebook.values()if len(x)>1)
        with self.assertRaises(ValueError):self.p.bytes(''.join(f'<h{i:02d}>'for i in word[:-1]))


if __name__=='__main__':unittest.main()
