import tkinter as tk
from PIL import Image, ImageTk
import ctypes

# Windows APIの定数を定義
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
LWA_ALPHA = 0x00000002

# DLLをロード
user32 = ctypes.windll.user32

def create_transparent_window(image_path):
    """
    指定した画像を半透明のウィンドウで表示し、マウス操作を透過させます。
    この機能はWindows OSでのみ動作します。
    """
    # メインウィンドウを作成
    root = tk.Tk()
    root.title("透過レイヤー")

    # ウィンドウをフレームレス（枠なし）にする
    root.overrideredirect(True)

    # ウィンドウを常に最前面に表示する
    root.attributes('-topmost', True)

    # ウィンドウの不透明度を設定
    # これだけだとマウス操作は透過しない
    root.attributes('-alpha', 0.6)

    hwnd = user32.GetParent(root.winfo_id())

    # ウィンドウに透過クリックのスタイルを設定
    # WS_EX_TRANSPARENT フラグがマウス操作を透過させる
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)

    try:
        # Pillowを使って画像を読み込む
        pil_image = Image.open(image_path)
        # 画像をTkinterで扱える形式に変換
        tk_image = ImageTk.PhotoImage(pil_image)

        # 画像を表示するラベルを作成
        image_label = tk.Label(root, image=tk_image, bg="white")
        image_label.pack(fill=tk.BOTH, expand=True)

        # ウィンドウのサイズを画像に合わせる
        root.geometry(f"{pil_image.width}x{pil_image.height}")

    except FileNotFoundError:
        print(f"エラー: 指定された画像ファイル '{image_path}' が見つかりません。")
        root.destroy()
        return

    # ウィンドウを閉じるためのイベントを設定
    # ESCキーで終了できるようにする
    root.bind('<Escape>', lambda e: root.destroy())

    # ウィンドウの位置を画面の中心に設定
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width / 2) - (pil_image.width / 2)
    y = (screen_height / 2) - (pil_image.height / 2)
    root.geometry(f'+{int(x)}+{int(y)}')
    
    # ウィンドウのドラッグ移動機能
    # マウス透過設定をするとドラッグも透過してしまうため、一旦スタイルを戻してから移動する
    def start_move(event):
        nonlocal style
        # ドラッグ中は透過設定を解除
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
        root.x = event.x
        root.y = event.y

    def stop_move(event):
        # ドラッグ終了後に透過設定を再度適用
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
        root.x = None
        root.y = None

    def do_move(event):
        if root.x is not None:
            dx = event.x - root.x
            dy = event.y - root.y
            root.geometry(f'+{root.winfo_x() + dx}+{root.winfo_y() + dy}')

    image_label.bind("<ButtonPress-1>", start_move)
    image_label.bind("<ButtonRelease-1>", stop_move)
    image_label.bind("<B1-Motion>", do_move)

    # メインループの開始
    root.mainloop()

if __name__ == '__main__':
    # 使用例: 'sample_image.png'という画像を透過レイヤーとして表示
    # 実行前に、このスクリプトと同じディレクトリに画像ファイルを置いてください。
    create_transparent_window('sample_image.png')