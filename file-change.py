from flask import Flask, request, render_template_string, send_file, after_this_request
from PIL import Image
import subprocess, os, tempfile, mimetypes
from io import BytesIO

app = Flask(__name__)

# 対応フォーマット（合計20種）
IMG_FORMATS   = {'jpg', 'png', 'bmp', 'gif', 'tiff', 'webp', 'ico'}      # 7種
AUDIO_FORMATS = {'mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a', 'wma'}         # 7種
VIDEO_FORMATS = {'mp4', 'avi', 'mkv', 'mov', 'webm', 'wmv'}                # 6種

# Pillow用のフォーマット名マッピング
PIL_FORMATS = {
    'jpg': 'JPEG',
    'jpeg': 'JPEG',
    'png': 'PNG',
    'bmp': 'BMP',
    'gif': 'GIF',
    'tiff': 'TIFF',
    'webp': 'WEBP',
    'ico': 'ICO'
}

def get_category(ext):
    ext = ext.lower()
    if ext in IMG_FORMATS:
        return 'image'
    elif ext in AUDIO_FORMATS:
        return 'audio'
    elif ext in VIDEO_FORMATS:
        return 'video'
    return None

@app.route("/", methods=["GET"])
def index():
    html = """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>メディアファイル変換サイト</title>
      <!-- Bootstrap CSS -->
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
      <style>
          body {
              background: #f7f7f7;
          }
          .container {
              max-width: 500px;
              margin-top: 50px;
              padding: 20px;
              background: #fff;
              border-radius: 8px;
              box-shadow: 0 4px 8px rgba(0,0,0,0.1);
          }
      </style>
    </head>
    <body>
      <div class="container">
        <h2 class="mb-4 text-center">ハイパーファイル形式コンバーター</h2>
        <form action="/convert" method="post" enctype="multipart/form-data">
          <div class="mb-3">
            <label for="fileInput" class="form-label">変換するファイルを選択</label>
            <input type="file" class="form-control" id="fileInput" name="file" required>
          </div>
          <div class="mb-3">
            <label for="targetFormat" class="form-label">変換先フォーマット</label>
            <select class="form-select" id="targetFormat" name="target_format" required>
              <option value="">ファイルを選択してください</option>
            </select>
          </div>
          <div class="d-grid">
            <button type="submit" class="btn btn-primary">変換</button>
          </div>
        </form>
      </div>
      
      <!-- Bootstrap JS and dependencies (optional) -->
      <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
      
      <script>
        const imgFormats = ['jpg', 'png', 'bmp', 'gif', 'tiff', 'webp', 'ico'];
        const audioFormats = ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a', 'wma'];
        const videoFormats = ['mp4', 'avi', 'mkv', 'mov', 'webm', 'wmv'];

        document.getElementById('fileInput').addEventListener('change', function() {
          const filePath = this.value;
          const fileName = filePath.split('\\\\').pop().split('/').pop();
          const parts = fileName.split('.');
          const ext = parts.length > 1 ? parts.pop().toLowerCase() : "";
          const targetSelect = document.getElementById('targetFormat');
          targetSelect.innerHTML = "";
          let options = [];
          
          if (imgFormats.includes(ext)) {
            options = imgFormats;
          } else if (audioFormats.includes(ext)) {
            options = audioFormats;
          } else if (videoFormats.includes(ext)) {
            options = videoFormats;
          }

          if (options.length === 0) {
            const opt = document.createElement('option');
            opt.value = "";
            opt.text = "サポートされていない形式";
            targetSelect.appendChild(opt);
            targetSelect.disabled = true;
          } else {
            targetSelect.disabled = false;
            options.forEach(function(fmt) {
              const opt = document.createElement('option');
              opt.value = fmt;
              opt.text = fmt;
              targetSelect.appendChild(opt);
            });
          }
        });
      </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route("/convert", methods=["POST"])
def convert():
    if 'file' not in request.files:
        return "ファイルがアップロードされていません", 400
    file = request.files['file']
    if file.filename == "":
        return "ファイルが選択されていません", 400
    target_format = request.form.get("target_format").lower()
    input_filename = file.filename
    ext = os.path.splitext(input_filename)[1].lower().lstrip('.')
    src_category = get_category(ext)
    target_category = get_category(target_format)
    if src_category is None or target_category is None or src_category != target_category:
        return "入力ファイルと変換先フォーマットのカテゴリが一致しません", 400

    if src_category == 'image':
        try:
            img = Image.open(file.stream)
            pil_format = PIL_FORMATS.get(target_format, target_format.upper())
            # JPEGの場合、RGBAやLAモードはRGBに変換する
            if pil_format == 'JPEG' and img.mode in ('RGBA', 'LA'):
                img = img.convert('RGB')
            output_io = BytesIO()
            img.save(output_io, format=pil_format)
            output_io.seek(0)
            mime = mimetypes.guess_type("output." + target_format)[0] or "application/octet-stream"
            return send_file(output_io, mimetype=mime, as_attachment=True, download_name="converted." + target_format)
        except Exception as e:
            return "変換エラー: " + str(e), 500
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix="." + ext) as temp_in:
            file.save(temp_in)
            temp_in.flush()
            input_path = temp_in.name
        output_path = tempfile.mktemp(suffix="." + target_format)
        try:
            cmd = ["ffmpeg", "-y", "-i", input_path, output_path]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                return "変換エラー: " + result.stderr.decode("utf-8"), 500
            @after_this_request
            def remove_temp(response):
                try:
                    os.remove(input_path)
                except Exception as e:
                    print(e)
                try:
                    os.remove(output_path)
                except Exception as e:
                    print(e)
                return response
            return send_file(output_path, as_attachment=True, download_name="converted." + target_format)
        except Exception as e:
            try:
                os.remove(input_path)
            except:
                pass
            try:
                os.remove(output_path)
            except:
                pass
            return "変換エラー: " + str(e), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=8012, debug=True)
