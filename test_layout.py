from PIL import Image, ImageDraw
import math

def apply_thumbnail_layout(img: Image.Image) -> Image.Image:
    width, height = img.size
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    shift_y = int(height * 0.22)
    canvas.paste(img, (0, shift_y))
    gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient)
    
    base_grad_end = int(height * 0.35)
    max_dip = int(height * 0.25)
    
    for x in range(width):
        nx = (x - width / 2) / (width / 2)
        y_shift = max_dip * (nx ** 6)
        local_grad_end = int(base_grad_end + y_shift)
        for y in range(local_grad_end):
            if y >= height:
                break
            ratio = y / local_grad_end
            alpha = int(255 * ((1 - ratio) ** 2))
            draw.point((x, y), fill=(0, 0, 0, alpha))
            
    return Image.alpha_composite(canvas, gradient)

img = Image.new("RGBA", (1024, 576), (255, 255, 255, 255))
out = apply_thumbnail_layout(img)
out.convert("RGB").save("test_out.jpg")
print("Done")
