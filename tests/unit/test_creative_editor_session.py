"""Tests for the tokenized Photopea editor session helpers."""

import json

from automation_hub.routers.creative import _parse_photopea_save_payload


def test_parse_photopea_save_payload_extracts_versions():
    psd_bytes = b"psd-binary"
    png_bytes = b"png-binary"
    header = json.dumps(
        {
            "source": "https://example.test/source.psd",
            "versions": [
                {"format": "psd:true", "start": 0, "size": len(psd_bytes)},
                {
                    "format": "png",
                    "start": len(psd_bytes),
                    "size": len(png_bytes),
                },
            ],
        }
    ).encode("utf-8")
    payload = header.ljust(2000, b" ") + psd_bytes + png_bytes

    meta, files = _parse_photopea_save_payload(payload)

    assert meta["source"] == "https://example.test/source.psd"
    assert [item["format"] for item in files] == ["psd", "png"]
    assert files[0]["bytes"] == psd_bytes
    assert files[1]["bytes"] == png_bytes
