from flask import Flask, request, render_template_string, send_file, after_this_request
import subprocess, os, tempfile

app = Flask(__name__)

@app.route("/")
def index():
  html = """
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>MP4動画圧縮サイト</title>
  <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500&display=swap" rel="stylesheet">
  <style>
  body {
    background: #f1f3f6;
    font-family: 'Roboto', sans-serif;
    margin: 0;
    padding: 0;
  }
  .container {
    max-width: 500px;
    margin: 5% auto;
    background: #fff;
    padding: 30px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    border-radius: 8px;
  }
  h1 {
    text-align: center;
    color: #333;
  }
  .info {
    font-size: 0.9em;
    color: #666;
    margin-bottom: 20px;
  }
  label {
    display: block;
    margin-top: 15px;
    color: #333;
  }
  input[type="file"],
  input[type="range"],
  input[type="submit"] {
    width: 100%;
    padding: 10px;
    margin-top: 5px;
    border: 1px solid #ccc;
    border-radius: 4px;
    box-sizing: border-box;
  }
  input[type="submit"] {
    background: #4CAF50;
    border: none;
    color: #fff;
    cursor: pointer;
    font-size: 1em;
    margin-top: 20px;
  }
  input[type="submit"]:hover {
    background: #45a049;
  }
  output {
    font-weight: bold;
    margin-left: 10px;
  }
  </style>
</head>
<body>
  <div class="container">
  <h1>MP4圧縮機</h1>
  <p class="info">
    <br>
    数値が小さいほど高画質・大容量になり、数値が大きいほど低画質・小容量になります。<br>
    一般的には、ちょっと圧縮する: 23 から 26 <br>けっこう品質ギリの結構圧縮: 35～（初期値は28）
  </p>
  <form action="/compress" method="post" enctype="multipart/form-data">
    <label for="video">動画ファイル (MP4のみ):</label>
    <input type="file" name="video" id="video" accept="video/mp4" required>
    
    <label for="crf">圧縮レベル (CRF): <output id="crfOutput">28</output></label>
    <input type="range" name="crf" id="crf" min="23" max="48" step="1" value="28" oninput="document.getElementById('crfOutput').value = this.value">
    
    <input type="submit" value="圧縮開始">
  </form>
  </div>
</body>
</html>
"""
  return render_template_string(html)

@app.route("/compress", methods=["POST"])
def compress():
  if "video" not in request.files:
    return "ファイルがアップロードされていません", 400
  file = request.files["video"]
  if file.filename == "":
    return "ファイルが選択されていません", 400
  
  # 送信されたCRF値を取得（初期値は28）
  crf_value = request.form.get("crf", "28")
  try:
    crf_int = int(crf_value)
    if crf_int < 23 or crf_int > 48:
      return "圧縮レベルは23から48の間で指定してください", 400
  except ValueError:
    return "無効な圧縮レベルです", 400

  # 入力動画を一時ファイルに保存
  with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_in:
    file.save(temp_in)
    temp_in.flush()
    input_path = temp_in.name

  # 圧縮後動画の出力先一時ファイル
  output_path = tempfile.mktemp(suffix=".mp4")
  try:
    # ffmpeg により動画圧縮（-crfで画質調整）
    cmd = ["ffmpeg", "-y", "-i", input_path, "-vcodec", "libx264", "-crf", str(crf_int), output_path]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
      return "圧縮エラー: " + result.stderr.decode("utf-8"), 500

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

    return send_file(output_path, as_attachment=True, download_name="compressed.mp4", mimetype="video/mp4")
  except Exception as e:
    try:
      os.remove(input_path)
    except:
      pass
    try:
      os.remove(output_path)
    except:
      pass
    return "圧縮エラー: " + str(e), 500

if __name__ == "__main__":
  app.run(host="0.0.0.0", port=8015, debug=True)
