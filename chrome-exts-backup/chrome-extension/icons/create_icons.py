#!/usr/bin/env python3
"""Create simple colored icons for Chrome extension"""

from PIL import Image, ImageDraw
import os


def create_icon(size, color="#3b82f6", filename="icon.png"):
    """Create a simple colored circle icon"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw filled circle
    margin = size // 8
    draw.ellipse([margin, margin, size - margin, size - margin], fill=color)

    # Save
    img.save(filename)
    print(f"Created {filename}")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Create icons in different sizes
    create_icon(16, "#3b82f6", "icon16.png")
    create_icon(32, "#3b82f6", "icon32.png")
    create_icon(48, "#3b82f6", "icon48.png")
    create_icon(128, "#3b82f6", "icon128.png")

    print("All icons created successfully!")
