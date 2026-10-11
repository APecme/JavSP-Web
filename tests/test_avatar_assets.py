import unittest
from PIL import Image, ImageDraw
from scripts.build_avatars import center_portrait


class AvatarCropTests(unittest.TestCase):
    def test_letterbox_edges_are_removed_before_center_crop(self):
        image = Image.new('RGB', (210, 280), 'black')
        ImageDraw.Draw(image).rectangle((0, 60, 209, 219), fill=(130, 150, 170))
        cropped = center_portrait(image)
        self.assertEqual(cropped.size, (128, 128))
        self.assertEqual(cropped.getpixel((0, 0)), (130, 150, 170))
        self.assertEqual(cropped.getpixel((127, 127)), (130, 150, 170))

    def test_portrait_crop_keeps_vertical_center(self):
        image = Image.new('RGB', (210, 280), 'white')
        ImageDraw.Draw(image).rectangle((0, 139, 209, 140), fill=(255, 0, 0))
        cropped = center_portrait(image)
        reds = [y for y in range(128) if cropped.getpixel((64, y))[1] < 200]
        self.assertTrue(reds)
        self.assertAlmostEqual(sum(reds)/len(reds), 63.5, delta=1)
