"""
PSD File Processor using psd-tools and PIL.
Moved from top-level psd_processor.py into automation_hub.services.
"""

import io
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from urllib.request import urlopen

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from psd_tools import PSDImage

from automation_hub.services.font_manager import get_font_dir
from automation_hub.services.font_manager import resolve_font


class PSDProcessor:
    """Process PSD files without requiring Photoshop installation."""

    def __init__(self) -> None:
        self.supported_formats = ["psd", "psb"]

    def get_layer_info(self, psd_path: str) -> List[Dict[str, Any]]:
        """
        Extract layer information from PSD file.
        Returns list of layers with their names, types, and positions.
        """
        try:
            psd = PSDImage.open(psd_path)
            layers: List[Dict[str, Any]] = []

            def extract_layers(layer_group, path: str = "") -> None:
                """Recursively extract all layers."""
                for layer in layer_group:
                    layer_path = f"{path}/{layer.name}" if path else layer.name

                    layer_info: Dict[str, Any] = {
                        "name": layer.name,
                        "full_path": layer_path,
                        "type": type(layer).__name__,
                        "visible": layer.visible,
                        "bbox": layer.bbox if hasattr(layer, "bbox") else None,
                        "opacity": getattr(layer, "opacity", 255),
                    }

                    # Add text content if it's a text layer
                    if hasattr(layer, "text"):
                        try:
                            layer_info["text"] = layer.text
                            layer_info["is_text_layer"] = True
                        except Exception:
                            layer_info["is_text_layer"] = False
                    else:
                        layer_info["is_text_layer"] = False

                    layers.append(layer_info)

                    # Recursively process nested layers
                    if hasattr(layer, "layers"):
                        extract_layers(layer.layers, layer_path)

            extract_layers(psd)
            return layers
        except Exception as e:  # pragma: no cover - defensive
            raise Exception(f"Failed to read PSD file: {str(e)}") from e

    def render_composite_preview(
        self, psd_path: str, output_path: str, max_size: int = 1400
    ) -> str:
        """Render a flattened PSD canvas for the browser editor."""
        psd = PSDImage.open(psd_path)
        image = psd.composite()
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image.astype(np.uint8))
        image = image.convert("RGBA")
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, "PNG")
        return output_path

    def find_layer_by_name(self, psd: PSDImage, layer_name: str):
        """Find a layer by name recursively."""

        def search_layers(layer_group, target_name):
            for layer in layer_group:
                if layer.name == target_name:
                    return layer
                if hasattr(layer, "layers"):
                    found = search_layers(layer.layers, target_name)
                    if found:
                        return found
            return None

        return search_layers(psd, layer_name)

    def _load_font(self, font_size: int = 12, font_path: str | None = None):
        """Load a truetype font if available, otherwise fall back to PIL default."""
        size = max(8, int(font_size))
        candidates: List[Path | str] = []
        if font_path and os.path.exists(font_path):
            candidates.append(font_path)

        candidate_names = [
            "DejaVuSans.ttf",
            "DejaVuSans-Bold.ttf",
            "LiberationSans-Regular.ttf",
            "LiberationSans-Bold.ttf",
            "Arial.ttf",
            "arial.ttf",
        ]
        candidates.extend(candidate_names)

        font_dirs = [
            get_font_dir(),
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".fonts",
        ]
        for font_dir in font_dirs:
            if not font_dir.exists():
                continue
            for name in candidate_names:
                direct = font_dir / name
                if direct.exists():
                    candidates.append(direct)
            for pattern in ("*.ttf", "*.otf", "**/*.ttf", "**/*.otf"):
                try:
                    for match in font_dir.glob(pattern):
                        if match.is_file():
                            candidates.append(match)
                except Exception:
                    continue

        seen = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            try:
                return ImageFont.truetype(str(candidate), size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _text_width(self, draw: ImageDraw.ImageDraw, value: str, font) -> int:
        """Measure the rendered width for a single line of text."""
        box = draw.textbbox((0, 0), value or " ", font=font)
        return max(1, box[2] - box[0])

    def _wrap_text_to_width(
        self, draw: ImageDraw.ImageDraw, text: str, font, max_width: int
    ) -> List[str]:
        """Wrap text to fit inside a maximum width, including very long words."""
        raw_value = text or ""
        if not raw_value.strip():
            return [""]
        lines: List[str] = []
        for paragraph in raw_value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            value = paragraph.strip()
            if not value:
                lines.append("")
                continue

            tokens = value.split()
            if not tokens:
                lines.append(value)
                continue

            current = ""
            for token in tokens:
                trial = f"{current} {token}".strip() if current else token
                if self._text_width(draw, trial, font) <= max_width:
                    current = trial
                    continue

                if current:
                    lines.append(current)
                    current = ""

                if self._text_width(draw, token, font) <= max_width:
                    current = token
                    continue

                chunk = ""
                for char in token:
                    trial_chunk = f"{chunk}{char}"
                    if chunk and self._text_width(draw, trial_chunk, font) > max_width:
                        lines.append(chunk)
                        chunk = char
                    else:
                        chunk = trial_chunk
                current = chunk

            if current:
                lines.append(current)

        return lines or [""]

    def _measure_text_block(
        self, draw: ImageDraw.ImageDraw, lines: List[str], font, spacing: int
    ) -> tuple[int, int, List[int]]:
        """Measure a wrapped text block for the given font."""
        widths: List[int] = []
        heights: List[int] = []
        for line in lines:
            box = draw.textbbox((0, 0), line or " ", font=font)
            widths.append(max(1, box[2] - box[0]))
            heights.append(max(1, box[3] - box[1]))
        total_height = sum(heights) + spacing * max(0, len(lines) - 1)
        return (max(widths) if widths else 1, total_height, heights)

    def _fit_text_layout(
        self,
        text: str,
        max_width: int,
        max_height: int,
        font_path: str | None,
        preferred_size: int,
    ):
        """Find a font size and wrapped lines that fit inside the target bounds."""
        scratch = Image.new(
            "RGBA", (max(32, max_width), max(32, max_height)), (0, 0, 0, 0)
        )
        draw = ImageDraw.Draw(scratch)
        start_size = max(8, int(preferred_size or 12))
        start_size = min(start_size, max(8, min(max_height, max_width)))

        best = None
        for size in range(start_size, 5, -1):
            font = self._load_font(font_size=size, font_path=font_path)
            lines = self._wrap_text_to_width(draw, text, font, max_width)
            spacing = max(1, int(size * 0.18))
            text_width, text_height, line_heights = self._measure_text_block(
                draw, lines, font, spacing
            )
            if text_width <= max_width and text_height <= max_height:
                return font, lines, spacing, line_heights, text_width, text_height
            best = (font, lines, spacing, line_heights, text_width, text_height)

        if best is not None:
            return best

        font = self._load_font(font_size=8, font_path=font_path)
        lines = self._wrap_text_to_width(draw, text, font, max_width)
        spacing = 2
        text_width, text_height, line_heights = self._measure_text_block(
            draw, lines, font, spacing
        )
        return font, lines, spacing, line_heights, text_width, text_height

    def render_text_in_bbox(
        self,
        base_image: Image.Image,
        text: str,
        bbox: tuple,
        font_path: str | None = None,
        font_size: int = 12,
        color: tuple = (0, 0, 0),
        align: str = "left",
        vertical_align: str = "top",
    ) -> Image.Image:
        """Render text directly into a bounding box without flattening it into a thin raster strip."""
        img = base_image.copy()
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        left, top, right, bottom = [int(v) for v in bbox]
        width = max(1, right - left)
        height = max(1, bottom - top)

        min_height = max(int(font_size * 1.8), 28)
        if height < min_height:
            height = min_height
            bottom = top + height

        padding_x = 6
        padding_y = 4
        content_width = max(1, width - (padding_x * 2))
        content_height = max(1, height - (padding_y * 2))

        if len(color) == 3:
            fill = (int(color[0]), int(color[1]), int(color[2]), 255)
        else:
            fill = tuple(color)

        preferred_size = max(8, int(font_size or 12))
        font, lines, spacing, line_heights, text_width, text_height = (
            self._fit_text_layout(
                text,
                content_width,
                content_height,
                font_path,
                preferred_size,
            )
        )

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        if vertical_align == "middle":
            current_y = top + padding_y + max(0, (content_height - text_height) // 2)
        elif vertical_align == "bottom":
            current_y = top + padding_y + max(0, content_height - text_height)
        else:
            current_y = top + padding_y

        for line, line_height in zip(lines, line_heights):
            line_width = self._text_width(draw, line, font)
            x = left + padding_x
            if align == "center" and line_width < content_width:
                x += max(0, (content_width - line_width) // 2)
            elif align == "right" and line_width < content_width:
                x += max(0, content_width - line_width)
            draw.text((x, current_y), line, font=font, fill=fill)
            current_y += line_height + spacing

        img.alpha_composite(overlay)
        return img

    def _normalize_cell_value(self, value: Any) -> str:
        """Convert a spreadsheet cell value to a safe display string."""
        if value is None:
            return ""
        try:
            if value != value:
                return ""
        except Exception:
            pass
        return str(value).strip()

    def _load_image_from_value(self, image_value: str) -> Optional[Image.Image]:
        """Load an image from URL, absolute path, or local uploads-relative path."""
        value = (image_value or "").strip()
        if not value:
            return None

        parsed = urlparse(value)
        if parsed.scheme in ("http", "https"):
            with urlopen(value, timeout=15) as response:
                return Image.open(io.BytesIO(response.read())).convert("RGBA")

        candidates = []
        if parsed.scheme == "file" and parsed.path:
            candidates.append(Path(parsed.path))
        candidates.append(Path(value))
        candidates.append(Path("uploads") / value)
        candidates.append(Path("uploads") / Path(value).name)
        candidates.append(Path.cwd() / value)
        candidates.append(Path.cwd() / "uploads" / value)
        candidates.append(Path.cwd() / "uploads" / Path(value).name)

        seen = set()
        for candidate in candidates:
            try:
                resolved = candidate.expanduser().resolve(strict=False)
            except Exception:
                resolved = candidate
            key = str(resolved)
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists() and candidate.is_file():
                return Image.open(candidate).convert("RGBA")
        return None

    def replace_image_in_bbox(
        self,
        base_image: Image.Image,
        replacement_image: Image.Image,
        bbox: tuple,
    ) -> Image.Image:
        """Resize/crop a replacement image to cover a layer bounding box."""
        img = base_image.copy()
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        left, top, right, bottom = bbox
        width = max(1, int(right - left))
        height = max(1, int(bottom - top))

        replacement = replacement_image.copy().convert("RGBA")
        scale = max(width / replacement.width, height / replacement.height)
        resized = replacement.resize(
            (
                max(1, int(replacement.width * scale)),
                max(1, int(replacement.height * scale)),
            ),
            Image.Resampling.LANCZOS,
        )
        crop_left = max(0, (resized.width - width) // 2)
        crop_top = max(0, (resized.height - height) // 2)
        cropped = resized.crop(
            (crop_left, crop_top, crop_left + width, crop_top + height)
        )
        img.paste(cropped, (int(left), int(top)), cropped)
        return img

    def apply_watermark(
        self,
        img: Image.Image,
        watermark_type: str = "text",
        watermark_value: str = "",
        watermark_image_path: str = "",
        position: str = "bottom-right",
        opacity: float = 0.5,
        font_size: int = 24,
        font_path: str | None = None,
    ) -> Image.Image:
        """
        Apply watermark to image.
        watermark_type: "text" or "image"
        watermark_value: text string (if type is "text")
        watermark_image_path: path to watermark image (if type is "image")
        position: "top-left", "top-right", "bottom-left", "bottom-right", "center"
        opacity: 0.0 to 1.0
        """
        if watermark_type == "text" and not watermark_value:
            return img
        if watermark_type == "image" and (
            not watermark_image_path or not os.path.exists(watermark_image_path)
        ):
            return img

        # Create watermark layer
        if watermark_type == "text":
            # Create text watermark
            watermark = Image.new("RGBA", img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(watermark)
            font = self._load_font(font_size=font_size, font_path=font_path)

            # Get text size
            bbox = draw.textbbox((0, 0), watermark_value, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # Calculate position
            img_width, img_height = img.size
            if position == "top-left":
                x, y = 10, 10
            elif position == "top-right":
                x, y = img_width - text_width - 10, 10
            elif position == "bottom-left":
                x, y = 10, img_height - text_height - 10
            elif position == "bottom-right":
                x, y = img_width - text_width - 10, img_height - text_height - 10
            else:  # center
                x, y = (img_width - text_width) // 2, (img_height - text_height) // 2

            # Draw text with opacity
            alpha = int(255 * opacity)
            draw.text((x, y), watermark_value, fill=(255, 255, 255, alpha), font=font)
        else:  # image watermark
            watermark_img = Image.open(watermark_image_path).convert("RGBA")
            # Resize watermark to fit (max 30% of image size)
            max_size = min(img.size) * 0.3
            watermark_ratio = min(
                max_size / watermark_img.width, max_size / watermark_img.height
            )
            new_size = (
                int(watermark_img.width * watermark_ratio),
                int(watermark_img.height * watermark_ratio),
            )
            watermark_img = watermark_img.resize(new_size, Image.Resampling.LANCZOS)

            # Apply opacity
            alpha = watermark_img.split()[3]
            alpha = alpha.point(lambda p: int(p * opacity))
            watermark_img.putalpha(alpha)

            # Create watermark layer
            watermark = Image.new("RGBA", img.size, (255, 255, 255, 0))

            # Calculate position
            img_width, img_height = img.size
            wm_width, wm_height = watermark_img.size
            if position == "top-left":
                x, y = 10, 10
            elif position == "top-right":
                x, y = img_width - wm_width - 10, 10
            elif position == "bottom-left":
                x, y = 10, img_height - wm_height - 10
            elif position == "bottom-right":
                x, y = img_width - wm_width - 10, img_height - wm_height - 10
            else:  # center
                x, y = (img_width - wm_width) // 2, (img_height - wm_height) // 2

            watermark.paste(watermark_img, (x, y), watermark_img)

        # Composite watermark onto image
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        result = Image.alpha_composite(img, watermark)

        return result

    def process_psd(
        self,
        psd_path: str,
        data_row: Any,
        layer_mapping: Dict[str, str],
        output_dir: str,
        filename: str,
        output_format: str = "both",
        watermark_config: Optional[Dict[str, Any]] = None,
        font_path: str | None = None,
        layer_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, str]:
        """
        Process a single PSD file with data row.
        Returns paths to generated files.

        watermark_config: Optional dict with keys:
            - enabled: bool
            - type: "text" or "image"
            - value: text string or image path
            - position: "top-left", "top-right", "bottom-left", "bottom-right", "center"
            - opacity: float (0.0 to 1.0)
            - font_size: int (for text watermark)
        """
        try:
            # Open PSD file
            psd = PSDImage.open(psd_path)

            mapped_layers = []
            hidden_layers = []
            effective_layers = list(layer_mapping.keys())
            effective_layers.extend(
                name
                for name in (layer_overrides or {}).keys()
                if name not in layer_mapping
            )
            for layer_name in effective_layers:
                layer = self.find_layer_by_name(psd, layer_name)
                mapped_layers.append((layer_name, layer))
                if not layer:
                    continue
                try:
                    if getattr(layer, "visible", True):
                        hidden_layers.append((layer, True))
                        layer.visible = False
                    else:
                        hidden_layers.append((layer, False))
                except Exception:
                    pass

            # Get the composite image without the mapped original layers,
            # so replacement text/images do not stack on top of the old content.
            composite = psd.composite()

            for layer, was_visible in hidden_layers:
                try:
                    layer.visible = was_visible
                except Exception:
                    pass

            # Convert to PIL Image if needed
            if isinstance(composite, np.ndarray):
                if composite.dtype == np.uint8:
                    if len(composite.shape) == 3:
                        if composite.shape[2] == 4:
                            img = Image.fromarray(composite, "RGBA")
                        else:
                            img = Image.fromarray(composite, "RGB")
                    else:
                        img = Image.fromarray(composite)
                else:
                    composite = (composite * 255).astype(np.uint8)
                    if len(composite.shape) == 3 and composite.shape[2] == 4:
                        img = Image.fromarray(composite, "RGBA")
                    else:
                        img = Image.fromarray(composite, "RGB")
            else:
                img = composite

            # Process each layer mapping
            mapped_layer_lookup = {name: layer for name, layer in mapped_layers}
            for layer_name in effective_layers:
                try:
                    layer = mapped_layer_lookup.get(layer_name)
                    if not layer:
                        print(f"Warning: Layer '{layer_name}' not found")
                        continue

                    override = (layer_overrides or {}).get(layer_name) or {}
                    if override.get("enabled", True) is False:
                        continue
                    source = override.get("source", "column")
                    column_name = override.get("column") or layer_mapping.get(
                        layer_name
                    )
                    if source == "constant":
                        cell_value = self._normalize_cell_value(override.get("value"))
                    elif source == "image":
                        cell_value = self._normalize_cell_value(
                            override.get("image_file_id")
                        )
                    elif column_name:
                        cell_value = self._normalize_cell_value(data_row[column_name])
                    else:
                        continue

                    if hasattr(layer, "bbox") and layer.bbox:
                        bbox = layer.bbox
                        x, y = bbox[0], bbox[1]
                    else:
                        bbox = None
                        x, y = 0, 0
                        if hasattr(layer, "left") and hasattr(layer, "top"):
                            x, y = layer.left, layer.top

                    is_text_layer = False
                    if hasattr(layer, "text"):
                        try:
                            _ = layer.text
                            is_text_layer = True
                        except Exception:
                            is_text_layer = False

                    override_type = override.get("type")
                    if not is_text_layer or override_type == "image":
                        replacement_image = self._load_image_from_value(cell_value)
                        if replacement_image and bbox:
                            img = self.replace_image_in_bbox(
                                img, replacement_image, bbox
                            )
                        else:
                            print(
                                f"Warning: Non-text layer '{layer_name}' needs an image path/URL and valid bbox; got '{cell_value}'"
                            )
                        continue

                    font_size = 12
                    text_color = (0, 0, 0)
                    layer_font_path = font_path
                    override_font = resolve_font(str(override.get("font_id") or ""))
                    if override_font:
                        layer_font_path = str(override_font)

                    if hasattr(layer, "text") and hasattr(layer, "_engine"):
                        try:
                            engine = layer._engine
                            if hasattr(engine, "editor"):
                                editor = engine.editor
                                if hasattr(editor, "font_size"):
                                    font_size = editor.font_size
                                if hasattr(editor, "color"):
                                    color_obj = editor.color
                                    if hasattr(color_obj, "rgb"):
                                        rgb = color_obj.rgb
                                        text_color = (
                                            int(rgb[0]),
                                            int(rgb[1]),
                                            int(rgb[2]),
                                        )
                        except Exception:
                            pass

                    if bbox:
                        img = self.render_text_in_bbox(
                            img,
                            cell_value,
                            bbox,
                            font_path=layer_font_path,
                            font_size=int(override.get("font_size") or font_size),
                            color=text_color,
                            align="left",
                            vertical_align="top",
                        )
                    else:
                        img = self.render_text_in_bbox(
                            img,
                            cell_value,
                            (
                                x,
                                y,
                                x + max(120, len(cell_value) * 10),
                                y + max(40, font_size * 3),
                            ),
                            font_path=layer_font_path,
                            font_size=int(override.get("font_size") or font_size),
                            color=text_color,
                            align="left",
                            vertical_align="top",
                        )
                except Exception as e:
                    print(f"Error processing layer '{layer_name}': {str(e)}")
                    continue

            # Apply watermark if configured
            if watermark_config and watermark_config.get("enabled"):
                img = self.apply_watermark(
                    img,
                    watermark_type=watermark_config.get("type", "text"),
                    watermark_value=watermark_config.get("value", ""),
                    watermark_image_path=watermark_config.get("image_path", ""),
                    position=watermark_config.get("position", "bottom-right"),
                    opacity=watermark_config.get("opacity", 0.5),
                    font_size=watermark_config.get("font_size", 24),
                    font_path=font_path,
                )

            output_paths: Dict[str, str] = {}

            # Convert RGBA to RGB for formats that don't support alpha
            base_img = img.copy()
            if base_img.mode == "RGBA" and output_format not in [
                "png",
                "webp",
                "avif",
                "all",
            ]:
                background = Image.new("RGB", base_img.size, (255, 255, 255))
                background.paste(
                    base_img,
                    mask=base_img.split()[3] if len(base_img.split()) > 3 else None,
                )
                base_img = background

            # Handle "all" format - generate all formats
            formats_to_generate = []
            if output_format == "all":
                formats_to_generate = ["png", "webp", "avif", "pdf"]
            elif output_format == "both":
                formats_to_generate = ["png", "psd"]
            else:
                formats_to_generate = [output_format]

            if "png" in formats_to_generate:
                png_path = os.path.join(output_dir, f"{filename}.png")
                if img.mode == "RGBA":
                    png_img = img.copy()
                else:
                    png_img = img.convert("RGB")
                png_img.save(png_path, "PNG", quality=95)
                output_paths["png"] = png_path

            if "webp" in formats_to_generate:
                webp_path = os.path.join(output_dir, f"{filename}.webp")
                webp_img = img.copy()
                if webp_img.mode not in ["RGB", "RGBA"]:
                    webp_img = webp_img.convert("RGBA")
                webp_img.save(webp_path, "WEBP", quality=90)
                output_paths["webp"] = webp_path

            if "avif" in formats_to_generate:
                try:
                    avif_path = os.path.join(output_dir, f"{filename}.avif")
                    avif_img = img.copy()
                    if avif_img.mode not in ["RGB", "RGBA"]:
                        avif_img = avif_img.convert("RGBA")
                    # Check if AVIF is supported
                    avif_img.save(avif_path, "AVIF", quality=90)
                    output_paths["avif"] = avif_path
                except Exception as e:
                    print(
                        f"Warning: AVIF format not available (may require pillow-avif-plugin): {str(e)}"
                    )

            if "pdf" in formats_to_generate:
                try:
                    pdf_path = os.path.join(output_dir, f"{filename}.pdf")
                    pdf_img = base_img.copy()
                    if pdf_img.mode != "RGB":
                        pdf_img = pdf_img.convert("RGB")
                    pdf_img.save(pdf_path, "PDF", resolution=300.0)
                    output_paths["pdf"] = pdf_path
                except Exception as e:
                    print(f"Warning: PDF format not available: {str(e)}")

            if "psd" in formats_to_generate or output_format == "both":
                try:
                    print(
                        "Note: Full PSD saving with layers is limited. "
                        "Saving flattened PNG export instead."
                    )
                    png_path = os.path.join(output_dir, f"{filename}_psd_export.png")
                    img.save(png_path, "PNG")
                    output_paths["psd_export"] = png_path
                except Exception as e:
                    print(f"Error saving PSD export: {str(e)}")

            return output_paths
        except Exception as e:  # pragma: no cover - defensive
            raise Exception(f"Failed to process PSD file: {str(e)}") from e
