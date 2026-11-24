from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from game_covers import CDN, GameCovers, cdn_url, encode_cover


class GameCoverTests(unittest.TestCase):
    def test_palette_transparency_and_pixels(self):
        img = Image.new('P', (35, 47))
        img.putpalette([24, 42, 60, 128, 64, 32] + [0] * 762)
        img.putpixel((2, 3), 1)
        source = BytesIO()
        img.save(source, format='PNG', transparency=0, bits=1)
        data = encode_cover(source.getvalue())
        self.assertEqual(data[24:26], source.getvalue()[24:26])
        self.assertEqual(data[28], 1)
        with Image.open(BytesIO(data)) as result, Image.open(BytesIO(source.getvalue())) as original:
            self.assertEqual(result.getpalette(), original.getpalette())
            self.assertEqual(result.convert('RGBA').tobytes(), original.convert('RGBA').tobytes())

    def test_only_public_lobby_paths(self):
        for value in [CDN+'%2e%2e/pass.png', CDN+'x.png?token=1', CDN+'a%5cb.png',
                      'https://elsewhere.test/a.png', CDN+'x.svg', CDN+'a.png#fragment']:
            self.assertIsNone(cdn_url(value))
        self.assertEqual(cdn_url(CDN+'7 Monkeys.png'), CDN+'7%20Monkeys.png')

    def test_captured_image_and_hall_override(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'other/capture/response-capture'
            folder = root / 'captures' / ('a' * 32)
            bodies = folder / 'bodies'
            bodies.mkdir(parents=True)
            demo = root.parents[1] / 'demo'
            demo.mkdir()
            (demo / 'index.html').write_text('<article data-provider="pg"><img src="/demo/cover.jpg"><button data-launch="demo-game"></button></article>')
            Image.new('RGB', (9,12), 'red').save(demo/'cover.jpg')
            Image.new('RGBA', (8,11), 'blue').save(bodies/'000002.png')
            games = [dict(id=site, externalId=ext, name=name, metadata={'brand':brand,'imageUrl':CDN+'image.png'})
                     for site, ext, name, brand in [('one','1','Demo Game','pg'),('two','2','Other','pp')]]
            (bodies/'000001.json').write_text(json.dumps({'items':games}))
            rows = []
            for i, (url, filename) in enumerate([('https://sdstest.ink/api/v1/games/catalog','000001.json'), (CDN+'image.png','000002.png')],1):
                rows.append(dict(id=i,url=url,body='bodies/'+filename,size=(bodies/filename).stat().st_size,
                                 method='GET',status=200,state='complete'))
            (folder/'manifest.json').write_text(json.dumps({'rows':rows}))
            covers=GameCovers(root)
            with patch('game_covers.build_opener',side_effect=AssertionError('已有原图时不应访问网络')):
                self.assertEqual(covers.get('/game-covers/site/one.png'), covers.get('/game-covers/code/demo-game.png'))
                for route in ('site/two','code/other','brand/pp/2'):
                    data=covers.get('/game-covers/'+route+'.png')
                    self.assertEqual(data[28],1)
                    self.assertEqual(Image.open(BytesIO(data)).size,(8,11))
            with self.assertRaises(KeyError):
                covers.get('/game-covers/code/no-such-game.png')
