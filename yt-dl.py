from flask import Flask, request, send_file, render_template_string
import yt_dlp as youtube_dl
import os

app = Flask(__name__)

HTML_INDEX = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>YouTube Downloader</title>
    <style>
        body { background: #f5f5f5; font-family: Arial, sans-serif; text-align: center; padding-top: 100px; }
        .form-container { background: #fff; display: inline-block; padding: 30px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        input[type="text"] { width: 300px; padding: 10px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; }
        input[type="submit"] { padding: 10px 20px; background: #3498db; border: none; border-radius: 4px; color: #fff; cursor: pointer; }
        input[type="submit"]:hover { background: #2980b9; }
        .radio-container { margin-bottom: 15px; }
        /* オーバーレイ用スタイル */
        #loadingOverlay {
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background-color: rgba(0,0,0,0.5);
            color: #fff;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            font-size: 2em;
            z-index: 9999;
        }
    </style>
</head>
<body>
    <div class="form-container">
        <h2>いしころダウンローダー(仮)</h2>
        <p>めんどくさいためダウンロードの進捗は適当です。長かったり重かったりしたら結構時間かかります。もしかしたらサーバー再起かかるかもしれません。</p>
        <h2>サーバ負荷を軽減するため、絶対に4k動画や長時間動画などの大容量な動画は「 MP4 (Video)」でダウンロードしないでください。</h2>
        <p>なお、「クイックダウンロード」はyoutubeからファイル形式を変えずにそのままダウンロードします。そのため、再生できない場合があります(windows標準再生ソフトなど)。</p>
        <p>そのため、再生できない場合は「VLC media player」などの再生ソフトが別途必要な場合があります。</p>
        <form action="/download" method="post" id="downloadForm">
            <input type="text" name="url" placeholder="YouTubeの動画のURLを入力してください" required><br>
            <div class="radio-container">
                <label><input type="radio" name="format" value="mp4" checked> MP4 (Video)</label>
                <label style="margin-left: 15px;"><input type="radio" name="format" value="mp3"> MP3 (Audio)</label>
                <label style="margin-left: 15px;"><input type="radio" name="format" value="quick">MP4/クイックダウンロード</label>
            </div>
            <input type="submit" value="Download">
        </form>
    </div>

    <script>
        const form = document.getElementById('downloadForm');
        form.addEventListener('submit', function(event){
            // オーバーレイを作成して表示
            const overlay = document.createElement('div');
            overlay.id = 'loadingOverlay';
            overlay.innerHTML = '<div id="progressMessage">動画処理中</div>';
            document.body.appendChild(overlay);

            // フォーマットを取得して処理時間を調整
            const format = new FormData(form).get('format');
            const isMp3 = format === 'mp3';
            const isQuick = format === 'quick';
            const processingTime = isMp3 ? 4000 : (isQuick ? 2000 : 8000); // MP3の場合は半分の時間

            // 疑似的な進捗メッセージの更新
            setTimeout(function(){
                document.getElementById('progressMessage').innerText = 'エンコード中';
            }, processingTime);  

            setTimeout(function(){
                document.getElementById('progressMessage').innerText = '準備完了';
            }, processingTime + 4000);  

            setTimeout(function(){
                overlay.style.display = 'none';  // オーバーレイを非表示にする
            }, processingTime + 7000);  
        });
    </script>
</body>
</html>
"""

@app.route('/', methods=['GET'])
def index():
        return HTML_INDEX

@app.route('/download', methods=['POST'])
def download_video():
        url = request.form.get('url')
        download_format = request.form.get('format')
        if not url:
                return "URL is missing", 400

        outtmpl = './tmp/%(title)s'
        if not os.path.exists('./tmp'):
                os.makedirs('./tmp')

        # Set options based on selected format.
        if download_format == 'mp3':
                ydl_opts = {
                        'outtmpl': outtmpl + '.%(ext)s',
                        'format': 'bestaudio/best',
                        'noplaylist': True,
                        'nocheckcertificate': True,
                        'postprocessors': [{
                                'key': 'FFmpegExtractAudio',
                                'preferredcodec': 'mp3',
                                'preferredquality': '192',
                        }],
                }
        elif download_format == 'quick':
                ydl_opts = {
                        'outtmpl': outtmpl + '.%(ext)s',
                        'format': 'bestvideo+bestaudio/best',
                        'noplaylist': True,
                        'nocheckcertificate': True,
                        'merge_output_format': 'mp4'
                }
        else:  # mp4
                ydl_opts = {
                        'outtmpl': outtmpl + '.%(ext)s',
                        'format': 'bestvideo+bestaudio/best',
                        'noplaylist': True,
                        'nocheckcertificate': True,
                        'merge_output_format': 'mp4'
                }

        try:
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        filepath = ydl.prepare_filename(info)

                # Adjust filepath extension if necessary
                if download_format == 'mp3':
                        filepath = os.path.splitext(filepath)[0] + '.mp3'
                elif download_format == 'quick':
                        filepath = os.path.splitext(filepath)[0] + '.mp4'
                else:
                        filepath = os.path.splitext(filepath)[0] + '.mp4'
                        # 再エンコード処理：ダウンロードした動画を一般的なH.264/AACに変換
                        converted_filepath = os.path.splitext(filepath)[0] + '_converted.mp4'
                        import subprocess
                        cmd = [
                                "ffmpeg", "-y", "-i", filepath,
                                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                                "-c:a", "aac", "-b:a", "128k",
                                converted_filepath
                        ]
                        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        if result.returncode == 0:
                                filepath = converted_filepath
                        else:
                                # 変換に失敗した場合はエラー出力（あるいは元ファイルを送信する）
                                raise Exception("ffmpeg変換エラー: " + result.stderr.decode("utf-8"))
                        
                # Return file as download
                return send_file(filepath, as_attachment=True)
        except Exception as e:
                error_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>Error</title>
    <style>
        body {{ background: #f8d7da; color: #721c24; font-family: Arial, sans-serif; text-align: center; padding-top: 100px; }}
        .error-container {{ display: inline-block; background: #f5c6cb; padding: 20px; border-radius: 8px; }}
        a {{ color: #721c24; text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="error-container">
        <h2>An error occurred</h2>
        <p>{str(e)}</p>
        <a href="/">Back</a>
    </div>
</body>
</html>"""
                return render_template_string(error_html), 500

if __name__ == '__main__':
        app.run(host="0.0.0.0",port=8022,debug=True)