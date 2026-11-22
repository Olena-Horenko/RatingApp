import unittest
 
from text_utils import sort_key
 
 
class SortKeyTests(unittest.TestCase):
 
    def test_ukrainian_alphabet_order(self):
        names = ["Яковенко", "Петренко", "Іваненко", "Єфременко",
                 "Ґудзь", "Гнатюк", "Андрієнко", "Їжакевич", "Йосипчук"]
 
        self.assertEqual(
            sorted(names, key=sort_key),
            ["Андрієнко", "Гнатюк", "Ґудзь", "Єфременко", "Іваненко",
             "Їжакевич", "Йосипчук", "Петренко", "Яковенко"]
        )
 
    def test_case_is_ignored(self):
        self.assertEqual(sort_key("ІВАН"), sort_key("іван"))
 
    def test_space_goes_before_letters(self):
        names = ["Петренко Іван", "Петренков Іван", "Петренко Анна"]
 
        self.assertEqual(
            sorted(names, key=sort_key),
            ["Петренко Анна", "Петренко Іван", "Петренков Іван"]
        )
 
    def test_apostrophe_is_ignored(self):
        self.assertEqual(sort_key("Дар'я"), sort_key("Дарʼя"))
        self.assertEqual(sort_key("Дар'я"), sort_key("Даря"))
 
    def test_none_and_numbers(self):
        self.assertEqual(sort_key(None), ())
        self.assertEqual(sort_key(5), sort_key("5"))
 
 
if __name__ == "__main__":
    unittest.main()
