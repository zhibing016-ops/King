import unittest
from systems.reaction_roles.services.panels import validate_customization
class CustomizationTests(unittest.TestCase):
    def test_valid(self):
        v=validate_customization('Título','Descrição','#123ABC','https://example.com/thumb.png','https://example.com/banner.png','Rodapé')
        self.assertEqual(v['color'],0x123ABC)
    def test_empty(self):
        self.assertEqual(validate_customization('T','D','#FFFFFF')['image_url'],'')
    def test_invalid_color(self):
        with self.assertRaises(ValueError): validate_customization('T','D','vermelho')
    def test_invalid_image(self):
        with self.assertRaises(ValueError): validate_customization('T','D','#FFFFFF','http://example.com/a.png')
    def test_invalid_footer(self):
        with self.assertRaises(ValueError): validate_customization('T','D','#FFFFFF',footer='x'*2049)
