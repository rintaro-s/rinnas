from PIL import Image

# 画像の読み込み
img = Image.open(r"E:\files\images\77c5ef4975e424d10710f7860a1a3553_upscayl_11x_digital-art-4x.png")

# 倍率を設定
scale = 10  # ここを好きな倍率に変更（例: 2, 3, 5, 10...）

# 元のサイズ
w, h = img.size

# 新しいサイズに拡大
new_size = (w * scale, h * scale)
img_resized = img.resize(new_size, Image.BICUBIC)

# 保存
img_resized.save(r"E:\files\images\output.png")

print(f"画像を {scale} 倍に拡大しました！サイズ: {new_size}")
