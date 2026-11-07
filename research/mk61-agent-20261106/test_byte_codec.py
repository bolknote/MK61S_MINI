import collections
import random
import unittest

from byte_codec import Codec,huffman


class CodecTests(unittest.TestCase):
    def test_all_bytes_and_random_programs(self):
        rng=random.Random(6114401)
        for radix in [2,16,32,64,256]:
            codec=Codec(huffman({0:20000,80:10000},radix),radix)
            self.assertEqual(codec.decode(codec.encode(range(256))),list(range(256)))
            for _ in range(12):
                code=[rng.randrange(256)for _ in range(rng.randrange(1,106))]
                self.assertEqual(codec.decode(codec.encode(code),105),code)

    def test_malformed_and_bounds(self):
        codec=Codec(huffman({0:10000},32),32)
        word=next(x for x in codec.codebook.values()if len(x)>1)
        with self.assertRaises(ValueError):codec.decode(word[:-1])
        with self.assertRaises(ValueError):codec.decode([32])
        with self.assertRaises(ValueError):codec.decode(codec.encode([0]*106),105)
        with self.assertRaises(ValueError):codec.encode([256])

    def test_frequent_symbol_gets_shorter_word(self):
        code=huffman(collections.Counter({96:10000,80:5000,16:2500}),32)
        self.assertEqual(len(code[96]),1)
        self.assertGreater(max(map(len,code.values())),1)
        self.assertTrue(all(len(x)==1 for x in huffman({},256).values()))


if __name__=='__main__':unittest.main()
