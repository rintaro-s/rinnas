from PIL import Image
Image.MAX_IMAGE_PIXELS = None 

# 画像の読み込み
img = Image.open(r"C:\Users\s-rin\Documents\GitHub\Rinnas\japan-04s_upscayl_14x_digital-art-4x.png")

# 倍率を設定
scale = 2  # ここを好きな倍率に変更（例: 2, 3, 5, 10...）

# 元のサイズ
w, h = img.size

# 新しいサイズに拡大
new_size = (w * scale, h * scale)
img_resized = img.resize(new_size, Image.BICUBIC)

# 保存
img_resized.save(r"E:\files\images\map.png")

print(f"画像を {scale} 倍に拡大しました！サイズ: {new_size}")
