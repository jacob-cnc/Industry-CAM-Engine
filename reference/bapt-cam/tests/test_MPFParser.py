import unittest

from .MPFParser import MPFParser


class TestMPFParser(unittest.TestCase):
    def test_parse(self):
        content = 'M30'
        parser = MPFParser(content)
        operations = parser.parse()
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0]['Type'], 'mcode')
        self.assertEqual(operations[0]['M'], ['M30'])

if __name__ == '__main__':
    unittest.main()

