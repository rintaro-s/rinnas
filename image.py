import os
import sys
import torch
from PIL import Image
from PIL import Image
Image.MAX_IMAGE_PIXELS = None  # Pillowの画像サイズ制限を解除

#pip install pillow tqdm numpy opencv-python
#python -c "import site,sys; print(site.getsitepackages()); import sys; print(sys.path)"
#C:\Users\s-rin\AppData\Local\Programs\Python\Python310\lib\site-packages
# try:
#     from torchvision.transforms.functional import rgb_to_grayscale
# except ImportError:
#     from torchvision.transforms.functional_tensor import rgb_to_grayscale


from tqdm import tqdm
from realesrgan import RealESRGANer
from basicsr.archs.rrdbnet_arch import RRDBNet
import numpy as np

# 画像高解像度化スクリプト
# 実行例: python image_upscale.py input.png output.png 4
# 引数: 入力画像, 出力画像, 倍率

def upscale_image(input_path, output_path, scale=4, tile=0, half=False):
    # モデルの設定
    model = RRDBNet(
        num_in_ch=3,
        num_out_ch=3,
        num_feat=64,
        num_block=23,
        num_grow_ch=32,
        scale=4
    )

    # デバイス選択
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"デバイス: {device}")

    # RealESRGANer初期化
    upsampler = RealESRGANer(
        scale=5,
        model_path='https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth',
        model=model,
        tile=64,
        tile_pad=10,
        pre_pad=0,
        half=False,
        device='cpu'
    )
    img = Image.open(input_path).convert('RGB')
    img = np.array(img)  # PIL → numpyに変換

    output, _ = upsampler.enhance(img, outscale=scale)

    # 出力画像を保存
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    output = Image.fromarray(output)
    output.save(output_path)
    print(f"完了！出力: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("使い方: python image_upscale.py 入力画像 出力画像 倍率")
        sys.exit(1)

    input_img = sys.argv[1]
    output_img = sys.argv[2]
    scale = int(sys.argv[3])

    upscale_image(input_img, output_img, scale=scale, tile=512, half=False)
