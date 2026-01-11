from flask import Flask, request, send_file, render_template_string
from werkzeug.utils import secure_filename
import yt_dlp as youtube_dl
import os

app = Flask(__name__)

HTML_INDEX = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>YouTube Downloader</title>
    <style>
        from flask import Flask, request, send_file, render_template_string
        from werkzeug.utils import secure_filename
        import yt_dlp as youtube_dl
        import os
        import uuid
        import subprocess
        import glob

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
                        <form action="/download" method="post" id="downloadForm" enctype="multipart/form-data">
                                <input type="text" name="url" placeholder="YouTubeの動画のURLを入力してください" required><br>
                                <div style="margin:8px 0; font-size:0.9em; color:#666;">(オプション) ログインが必要な動画や年齢制限、地域制限がある場合はブラウザからエクスポートした cookies.txt を指定してください。</div>
                                <input type="file" name="cookies" accept=".txt"><br>
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

                # ensure tmp and cookies dirs exist
                if not os.path.exists('./tmp'):
                        os.makedirs('./tmp')
                if not os.path.exists('./cookies'):
                        os.makedirs('./cookies')

                # If a cookies file was uploaded, save it
                cookiefile_path = None
                cookies_file = request.files.get('cookies')
                if cookies_file and cookies_file.filename:
                        safe_name = secure_filename(cookies_file.filename)
                        cookiefile_path = os.path.join('./cookies', safe_name)
                        cookies_file.save(cookiefile_path)

                # Define format strategies
                mp4_first = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
                generic_best = 'bestvideo+bestaudio/best'
                audio_only = 'bestaudio/best'

                if download_format == 'mp3':
                        format_strategies = [audio_only]
                elif download_format == 'quick':
                        format_strategies = [generic_best, mp4_first]
                else:
                        format_strategies = [mp4_first, generic_best, audio_only]

                default_http_headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                                                  'Chrome/117.0.0.0 Safari/537.36',
                }

                unique_id = uuid.uuid4().hex
                outtmpl_unique = f"./tmp/%(title)s_{unique_id}"

                final_filepath = None
                last_error = None

                # Try each strategy with retries
                for fmt in format_strategies:
                        for attempt in range(1, 4):
                                ydl_opts_try = {
                                        'outtmpl': outtmpl_unique + '.%(ext)s',
                                        'format': fmt,
                                        'noplaylist': True,
                                        'nocheckcertificate': True,
                                        'http_headers': default_http_headers,
                                        'socket_timeout': 30,
                                        'retries': 3,
                                        'fragment_retries': 3,
                                        'noprogress': True,
                                }
                                if cookiefile_path:
                                        ydl_opts_try['cookiefile'] = cookiefile_path

                                if attempt >= 2:
                                        ydl_opts_try['geo_bypass'] = True
                                        ydl_opts_try['geo_bypass_country'] = 'US'

                                try:
                                        with youtube_dl.YoutubeDL(ydl_opts_try) as ydl:
                                                info = ydl.extract_info(url, download=True)
                                                filepath = ydl.prepare_filename(info)
                                        final_filepath = filepath
                                        last_error = None
                                        break
                                except Exception as e:
                                        last_error = e
                                        # cleanup partial files for this outtmpl
                                        try:
                                                candidate = outtmpl_unique + '.*'
                                                for p in glob.glob(candidate):
                                                        try:
                                                                os.remove(p)
                                                        except:
                                                                pass
                                        except:
                                                pass
                                        if attempt < 3:
                                                continue
                                        else:
                                                pass
                        if final_filepath:
                                break

                if not final_filepath:
                        err_msg = f"ダウンロードに失敗しました: {str(last_error)}"
                        error_html = """<!DOCTYPE html>
        <html lang="ja">
        <head>
                <meta charset="UTF-8">
                <title>Download Error</title>
                <style>
                        body { background: #fff7f7; color: #a33; font-family: Arial, sans-serif; text-align: center; padding-top: 80px; }
                        .container { display:inline-block; background:#fff; padding:20px; border-radius:8px; box-shadow:0 2px 6px rgba(0,0,0,0.1); }
                        a { color:#06c; text-decoration:underline }
                </style>
        </head>
        <body>
                <div class="container">
                        <h2>ダウンロードに失敗しました</h2>
                        <p>{{ err_msg }}</p>
                        <p>対処案: cookies.txt をアップロードして再試行、または別の動画を試してください。</p>
                        <a href="/">戻る</a>
                </div>
        </body>
        </html>"""
                        return render_template_string(error_html, err_msg=err_msg), 500

                # Normalize/convert if needed
                if download_format == 'mp3':
                        final_filepath = os.path.splitext(final_filepath)[0] + '.mp3'
                else:
                        ext = os.path.splitext(final_filepath)[1].lower()
                        if ext != '.mp4':
                                converted_filepath = os.path.splitext(final_filepath)[0] + '_converted.mp4'
                                cmd = [
                                        "ffmpeg", "-y", "-i", final_filepath,
                                        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                                        "-c:a", "aac", "-b:a", "128k",
                                        converted_filepath
                                ]
                                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                                if result.returncode == 0:
                                        final_filepath = converted_filepath
                                else:
                                        err_msg = "ffmpeg変換に失敗しました: " + result.stderr.decode('utf-8', errors='ignore')
                                        error_html = """<!DOCTYPE html>
        <html lang="ja">
        <head><meta charset="utf-8"><title>Conversion error</title></head>
        <body>
        <h2>変換に失敗しました</h2>
        <pre>{{ err_msg }}</pre>
        <p><a href="/">戻る</a></p>
        </body>
        </html>"""
                                        return render_template_string(error_html, err_msg=err_msg), 500

                return send_file(final_filepath, as_attachment=True)


        if __name__ == '__main__':
                app.run(host="0.0.0.0",port=8022,debug=True)

                try:
                        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                                info = ydl.extract_info(url, download=True)
                                filepath = ydl.prepare_filename(info)
                except Exception as first_err:
                        # If we get a 403 (Forbidden), retry with geo_bypass and same headers
                        err_str = str(first_err)
                        if 'HTTP Error 403' in err_str or '403' in err_str:
                                # If a cookiefile is available, try again with it
                                tried_retry = False
                                if cookiefile_path:
                                        retry_opts = dict(ydl_opts)
                                        retry_opts.update({
                                                'geo_bypass': True,
                                                'geo_bypass_country': 'US',
                                                'http_headers': default_http_headers,
                                                'cookiefile': cookiefile_path,
                                        })
                                        tried_retry = True
                                        try:
                                                with youtube_dl.YoutubeDL(retry_opts) as ydl:
                                                        info = ydl.extract_info(url, download=True)
                                                        filepath = ydl.prepare_filename(info)
                                        except Exception as second_err:
                                                # If retry failed, raise to outer handler
                                                raise second_err
                                # If no cookiefile was provided, suggest the user to upload cookies
                                if not tried_retry:
                                        raise first_err
                        else:
                                # Other errors: re-raise
                                raise first_err

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