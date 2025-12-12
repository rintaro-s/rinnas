from PIL import Image
import argparse

# 色パレット（PC-9801 8色）
PC98_COLORS = [
    (0, 0, 0),       # 0: 黒
    (0, 0, 255),     # 1: 青
    (0, 255, 0),     # 2: 緑
    (0, 255, 255),   # 3: 水色
    (255, 0, 0),     # 4: 赤
    (255, 0, 255),   # 5: 紫
    (255, 255, 0),   # 6: 黄
    (255, 255, 255), # 7: 白
]

def nearest_color(rgb):
    r, g, b = rgb
    best = 0
    best_dist = 1e9
    for i, (cr, cg, cb) in enumerate(PC98_COLORS):
        d = (r-cr)**2 + (g-cg)**2 + (b-cb)**2
        if d < best_dist:
            best_dist = d
            best = i
    return best

def convert_image(filename, mode="bw", optimize=False, width=41, height=41):
    img = Image.open(filename).convert("RGB").resize((width, height))
    data_lines = []

    for y in range(height):
        row = []
        for x in range(width):
            r,g,b = img.getpixel((x,y))
            if mode == "bw":
                val = 1 if (r+g+b)//3 < 128 else 0
            else:  # color
                val = nearest_color((r,g,b))
            row.append(str(val))

        if optimize:
            # 連続する同じ色をまとめる
            compressed = []
            prev = row[0]
            count = 1
            for v in row[1:]:
                if v == prev:
                    count += 1
                else:
                    compressed.append((prev, count))
                    prev, count = v, 1
            compressed.append((prev, count))
            data_lines.append(compressed)
        else:
            data_lines.append("".join(row))
    return data_lines

def generate_basic(data_lines, mode="bw", optimize=False):
    lines = []
    lines.append("10 SCREEN 5:CLS")
    if optimize:
        # LINEを使って圧縮した描画
        line_no = 20
        for y, row in enumerate(data_lines):
            for color, count in row:
                if color != "0":  # 黒は省略
                    x_start = sum(c for _,c in row[:row.index((color,count))])
                    x_end = x_start + count - 1
                    lines.append(f"{line_no} LINE({x_start},{y})-({x_end},{y}),{color}")
                    line_no += 10
        lines.append(f"{line_no} END")
    else:
        lines.append("20 FOR Y=0 TO {}".format(len(data_lines)-1))
        lines.append("30 READ A$")
        lines.append("40 FOR X=0 TO LEN(A$)-1")
        lines.append("50 C=VAL(MID$(A$,X+1,1))")
        lines.append("60 IF C<>0 THEN PSET(X,Y),C")
        lines.append("70 NEXT X")
        lines.append("80 NEXT Y")
        lines.append("90 END")

        base = 100
        for row in data_lines:
            lines.append(f"{base} DATA {row}")
            base += 10
    return "\n".join(lines)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", help="入力PNGファイル")
    parser.add_argument("--mode", choices=["bw","color"], default="bw")
    parser.add_argument("--opt", action="store_true", help="最適化モード有効化")
    parser.add_argument("--w", type=int, default=41)
    parser.add_argument("--h", type=int, default=41)
    args = parser.parse_args()

    data_lines = convert_image(args.filename, mode=args.mode, optimize=args.opt, width=args.w, height=args.h)
    code = generate_basic(data_lines, mode=args.mode, optimize=args.opt)
    print(code)
