"""Focused tests for advanced PSD editor helpers."""

from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from automation_hub.services.psd_processor import PSDProcessor


def test_render_composite_preview_resizes_and_writes_png(tmp_path):
    composite = np.zeros((2000, 1000, 4), dtype=np.uint8)
    composite[:, :, 3] = 255
    fake_psd = type("FakePSD", (), {"composite": lambda self: composite})()
    output = tmp_path / "preview.png"

    with patch(
        "automation_hub.services.psd_processor.PSDImage.open",
        return_value=fake_psd,
    ):
        result = PSDProcessor().render_composite_preview(
            "template.psd", str(output), max_size=500
        )

    assert result == str(output)
    assert output.is_file()
    with Image.open(output) as image:
        assert image.size == (250, 500)


def test_replace_image_in_bbox_covers_target_area(tmp_path):
    processor = PSDProcessor()
    canvas = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    replacement = Image.new("RGBA", (20, 10), (255, 0, 0, 255))

    result = processor.replace_image_in_bbox(canvas, replacement, (10, 20, 60, 70))

    assert result.getpixel((35, 45)) == (255, 0, 0, 255)
    assert result.getpixel((0, 0)) == (255, 255, 255, 255)
