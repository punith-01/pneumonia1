"""Utilities
"""
import re
import base64

from PIL import Image
from io import BytesIO


def base64_to_pil(img_base64: str) -> Image.Image:
    """
    Convert base64 image data to PIL image.
    Ensures the image is in RGB format for model processing.
    """
    # Handle both formats: with and without data URL prefix
    if img_base64.startswith('data:image'):
        # Remove data URL prefix if present
        image_data = re.sub(r'^data:image/[^;]+;base64,', '', img_base64)
    else:
        # Already clean base64 data
        image_data = img_base64
    
    try:
        # Decode base64 to bytes
        image_bytes = base64.b64decode(image_data)
        pil_image = Image.open(BytesIO(image_bytes))
        
        # Convert to RGB if necessary (handles RGBA, grayscale, etc.)
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')
        
        return pil_image
    except Exception as e:
        raise ValueError(f"Invalid base64 image data: {e}") from e

