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
    <title>YouTube Downloader (fixed)</title>
    <style>
        body { background: #f5f5f5; font-family: Arial, sans-serif; text-align: center; padding-top: 100px; }
        .form-container { background: #fff; display: inline-block; padding: 30px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        input[type="text"] { width: 300px; padding: 10px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px; }
        input[type="submit"] { padding: 10px 20px; background: #3498db; border: none; border-radius: 4px; color: #fff; cursor: pointer; }
        input[type="submit"]:hover { background: #2980b9; }
        .radio-container { margin-bottom: 15px; }
        #loadingOverlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 2em; z-index: 9999; }
    </style>
</head>
<body>
    <div class="form-container">
        <h2>いしころダウンローダー (fixed)</h2>
        <p>403 や形式選択で失敗するケースを複数戦略で再試行する修正版です。</p>
        <form action="/download" method="post" id="downloadForm" enctype="multipart/form-data">
            <input type="text" name="url" placeholder="YouTubeの動画のURLを入力してください" required><br>
            <div style="margin:8px 0; font-size:0.9em; color:#666;">(オプション) cookies.txt を指定するとログインが必要な動画や年齢制限のある動画がダウンロードできる場合があります。</div>
            <input type="file" name="cookies" accept=".txt"><br>
            <div class="radio-container">
                <label><input type="radio" name="format" value="mp4" checked> MP4 (Video)</label>
                <label style="margin-left: 15px;"><input type="radio" name="format" value="mp3"> MP3 (Audio)</label>
                <label style="margin-left: 15px;"><input type="radio" name="format" value="quick">MP4/クイックダウンロード</label>
            </div>
            <input type="submit" value="Download">
        </form>
    </div>
    <div id="loadingOverlay" style="display:none;"><div id="progressMessage">処理中</div></div>
    <script>
        const form = document.getElementById('downloadForm');
        form.addEventListener('submit', function(event){
            document.getElementById('loadingOverlay').style.display = 'flex';
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
                # If user requested mp3, let yt-dlp run FFmpegExtractAudio postprocessor
                if download_format == 'mp3':
                    # prefer best audio and convert to mp3 with ffmpeg
                    ydl_opts_try['format'] = 'bestaudio/best'
                    ydl_opts_try['postprocessors'] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }]

                # Ensure merged video outputs are mp4 if possible (yt-dlp will still pick the best merging format)
                ydl_opts_try['merge_output_format'] = 'mp4'

                with youtube_dl.YoutubeDL(ydl_opts_try) as ydl:
                    info = ydl.extract_info(url, download=True)
                    # base filename (before any postprocessing): includes extension
                    base_filepath = ydl.prepare_filename(info)
                    # remove extension (we want base name for glob matching)
                    base_no_ext = os.path.splitext(base_filepath)[0]

                # locate actual downloaded file(s) under tmp matching base filepath prefix
                candidates = glob.glob(base_no_ext + '.*')
                # If postprocessor converted to mp3, prefer that
                chosen = None
                if download_format == 'mp3':
                    for c in candidates:
                        if c.lower().endswith('.mp3'):
                            chosen = c
                            break
                if not chosen and candidates:
                    # prefer mp4 if the UI asked for mp4, else pick first candidate
                    if download_format == 'mp4':
                        for c in candidates:
                            if c.lower().endswith('.mp4'):
                                chosen = c
                                break
                    if not chosen:
                        chosen = candidates[0]

                if not chosen:
                    # No file produced for this attempt/strategy — mark error and retry
                    last_error = f"No output file for base: {base_no_ext}; candidates: {candidates}"
                    # cleanup and continue to next attempt
                    try:
                        candidate = outtmpl_unique + '.*'
                        for p in glob.glob(candidate):
                            try:
                                os.remove(p)
                            except:
                                pass
                    except:
                        pass
                    continue

                final_filepath = chosen
                # debugging: log chosen/created file
                try:
                    print(f"[yt-dlp] Chosen output file: {final_filepath}")
                except Exception:
                    pass
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
    try:
        # find final file if glob path still points to base
        if not final_filepath or not os.path.exists(final_filepath):
            # try find with glob
            candidates = glob.glob(outtmpl_unique + '.*')
            if candidates:
                final_filepath = candidates[0]
    except Exception:
        pass

    if download_format == 'mp3':
        if not final_filepath or not final_filepath.lower().endswith('.mp3'):
            # if postprocessor did not produce mp3, convert using ffmpeg as fallback
            if final_filepath and os.path.exists(final_filepath):
                mp3_target = os.path.splitext(final_filepath)[0] + '.mp3'
                cmd = [
                    'ffmpeg', '-y', '-i', final_filepath,
                    '-vn', '-acodec', 'libmp3lame', '-ar', '44100', '-b:a', '192k',
                    mp3_target
                ]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode == 0 and os.path.exists(mp3_target):
                    final_filepath = mp3_target
                else:
                    err_msg = 'mp3変換に失敗しました: ' + result.stderr.decode('utf-8', errors='ignore')
                    error_html = """<!DOCTYPE html>
<html lang=\"ja\"> 
<head><meta charset=\"utf-8\"><title>Conversion error</title></head>
<body>
<h2>変換に失敗しました</h2>
<pre>{{ err_msg }}</pre>
<p><a href=\"/\">戻る</a></p>
</body>
</html>"""
                    return render_template_string(error_html, err_msg=err_msg), 500
            else:
                # nothing to convert
                err_msg = 'ダウンロード後のファイルが見つかりませんでした。'
                return render_template_string('<h2>{{err_msg}}</h2><p><a href="/">戻る</a></p>', err_msg=err_msg), 500
    else:
        # For video downloads, ensure we send an mp4; convert if necessary
        if final_filepath and os.path.exists(final_filepath):
            ext = os.path.splitext(final_filepath)[1].lower()
        else:
            # try to discover candidate
            candidates = glob.glob(outtmpl_unique + '.*')
            if candidates:
                final_filepath = candidates[0]
                ext = os.path.splitext(final_filepath)[1].lower()
            else:
                ext = ''

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

    # final sanity: ensure file exists
    if final_filepath:
        final_filepath = os.path.abspath(final_filepath)

    if not final_filepath or not os.path.exists(final_filepath):
        err_msg = 'ファイルが見つかりません: ' + str(final_filepath)
        return render_template_string('<h2>{{ err_msg }}</h2><p><a href="/">戻る</a></p>', err_msg=err_msg), 500
    try:
        print(f"[yt-dlp] Sending file: {final_filepath}")
    except Exception:
        pass

    return send_file(final_filepath, as_attachment=True)


if __name__ == '__main__':
    app.run(host="0.0.0.0",port=8022,debug=True)
