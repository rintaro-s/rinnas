import tkinter as tk
from PIL import Image, ImageTk, ImageDraw
import threading

Image.MAX_IMAGE_PIXELS = None

class TileViewer:
    def __init__(self, master, img_path):
        self.master = master
        self.img = Image.open(img_path).convert('RGB')
        self.window_w = 1200
        self.window_h = 800
        self.tile_size = 5000  # 元画像上のタイルサイズ

        # 最初は全体プレビュー
        preview_scale = min(self.window_w / self.img.width, self.window_h / self.img.height)
        self.preview_scale = preview_scale
        self.preview_img = self.img.resize(
            (int(self.img.width * preview_scale), int(self.img.height * preview_scale)),
            Image.Resampling.BILINEAR
        )

        # グリッド線
        draw = ImageDraw.Draw(self.preview_img)
        for x in range(0, self.img.width, self.tile_size):
            px = int(x * preview_scale)
            draw.line([(px, 0), (px, self.preview_img.height)], fill='blue', width=1)
        for y in range(0, self.img.height, self.tile_size):
            py = int(y * preview_scale)
            draw.line([(0, py), (self.preview_img.width, py)], fill='blue', width=1)

        self.tk_preview = ImageTk.PhotoImage(self.preview_img)

        # Canvas
        self.canvas = tk.Canvas(master, width=self.window_w, height=self.window_h)
        self.canvas.pack()
        self.canvas_img = self.canvas.create_image(0, 0, anchor='nw', image=self.tk_preview)

        self.focus_rect = None
        self.canvas.bind("<Button-1>", self.on_click)

    def on_click(self, event):
        # 元画像上のクリック位置
        x = int(event.x / self.preview_scale)
        y = int(event.y / self.preview_scale)

        # タイル領域
        left = max(0, x - self.tile_size // 2)
        top = max(0, y - self.tile_size // 2)
        right = min(left + self.tile_size, self.img.width)
        bottom = min(top + self.tile_size, self.img.height)

        # タイル表示（低解像度で軽く）
        threading.Thread(target=self.show_tile, args=(left, top, right, bottom)).start()

        # 赤枠でフォーカス表示
        self.draw_focus(left, top, right, bottom)

    def show_tile(self, left, top, right, bottom):
        tile = self.img.crop((left, top, right, bottom))
        # タイルをモニターサイズに合わせて低解像度表示
        display_w = self.window_w
        display_h = self.window_h
        tile_small = tile.resize((display_w, display_h), Image.Resampling.BILINEAR)
        self.tk_tile = ImageTk.PhotoImage(tile_small)
        self.canvas.itemconfig(self.canvas_img, image=self.tk_tile)

    def draw_focus(self, left, top, right, bottom):
        px_left = int(left * self.preview_scale)
        px_top = int(top * self.preview_scale)
        px_right = int(right * self.preview_scale)
        px_bottom = int(bottom * self.preview_scale)
        if self.focus_rect:
            self.canvas.delete(self.focus_rect)
        self.focus_rect = self.canvas.create_rectangle(
            px_left, px_top, px_right, px_bottom, outline='red', width=3
        )

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Huge Image Tile Viewer")
    viewer = TileViewer(root, r"E:\files\images\output.png") 
    root.mainloop()
