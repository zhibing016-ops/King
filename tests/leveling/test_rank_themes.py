from systems.leveling.cards.rank_card import make_rank_card, THEMES
from PIL import Image

def test_themes():
    for theme in THEMES:
        output = make_rank_card("Teste", 3000, 3, theme=theme, accent="#aabbcc")
        assert Image.open(output).size == (900, 280)
