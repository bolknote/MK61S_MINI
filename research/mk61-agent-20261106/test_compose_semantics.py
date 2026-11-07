import unittest

from compose_semantics import core_labels


class SemanticTargets(unittest.TestCase):
    def test_boundary_token_including_operator_is_supervised(self):
        # The token spanning >+ contains both markup and the root operation.
        ids=[10,11,12,13,14,15];offsets=[(0,1),(1,5),(5,7),(7,10),(10,12),(12,19)]
        self.assertEqual(core_labels(ids,offsets,6,12,2),[-100,-100,12,13,14,-100,2])

    def test_empty_semantics_cannot_silently_train_only_eos(self):
        with self.assertRaises(ValueError):core_labels([3],[(0,2)],6,10,2)


if __name__=='__main__':unittest.main()
