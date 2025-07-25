from flask import Flask, request, render_template_string
import requests

app = Flask(__name__)

# InvidiousインスタンスのURL
INVIDIOUS_URL = "https://invidious.io"

# 検索ページのHTMLテンプレート
SEARCH_TEMPLATE = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>Search - YouTube via Invidious</title>
    <style>
        body { font-family: Arial, sans-serif; }
        h1 { color: #333; }
        form { margin: 20px 0; }
        input[type="text"] { padding: 5px; width: 300px; }
        button { padding: 5px 10px; }
    </style>
</head>
<body>
    <h1>YouTube検索</h1>
    <form method="post" action="/search">
        <input type="text" name="query" placeholder="検索キーワードを入力" required>
        <button type="submit">検索</button>
    </form>
</body>
</html>
"""

# 検索結果ページのHTMLテンプレート
SEARCH_RESULTS_TEMPLATE = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>検索結果 - YouTube via Invidious</title>
    <style>
        body { font-family: Arial, sans-serif; }
        h1 { color: #333; }
        ul { list-style: none; padding: 0; }
        li { margin: 10px 0; }
        img { width: 120px; height: 90px; }
        a { text-decoration: none; color: #0066cc; }
    </style>
</head>
<body>
    <h1>検索結果</h1>
    <ul>
        {% for video in videos %}
        <li>
            <a href="/video/{{ video['videoId'] }}">
                <img src="{{ video['thumbnails'][0]['url'] }}" alt="サムネイル">
                {{ video['title'] }}
            </a>
        </li>
        {% endfor %}
    </ul>
</body>
</html>
"""

# 動画視聴ページのHTMLテンプレート
VIDEO_TEMPLATE = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>{{ video['title'] }} - YouTube via Invidious</title>
    <style>
        body { font-family: Arial, sans-serif; }
        h1 { color: #333; }
        video { width: 640px; height: 360px; }
        p { margin: 10px 0; }
        h2 { color: #666; }
        ul { list-style: none; padding: 0; }
        li { margin: 10px 0; }
        img { width: 120px; height: 90px; }
        a { text-decoration: none; color: #0066cc; }
    </style>
</head>
<body>
    <h1>{{ video['title'] }}</h1>
    <video controls>
        <source src="{{ format['url'] }}" type="{{ format['type'] }}">
        お使いのブラウザはビデオタグをサポートしていません。
    </video>
    <p>{{ video['description'] }}</p>
    <h2>関連動画</h2>
    <ul>
        {% for suggestion in suggestions %}
        <li>
            <a href="/video/{{ suggestion['videoId'] }}">
                <img src="{{ suggestion['thumbnails'][0]['url'] }}" alt="サムネイル">
                {{ suggestion['title'] }}
            </a>
        </li>
        {% endfor %}
    </ul>
</body>
</html>
"""

# エラーページのHTMLテンプレート
ERROR_TEMPLATE = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>エラー</title>
    <style>
        body { font-family: Arial, sans-serif; }
        h1 { color: #333; }
        p { color: #666; }
    </style>
</head>
<body>
    <h1>エラー</h1>
    <p>{{ message }}</p>
</body>
</html>
"""

@app.route('/')
def search_form():
    """検索フォームを表示するルート"""
    return render_template_string(SEARCH_TEMPLATE)

@app.route('/search', methods=['POST'])
def search():
    """検索クエリを受け取り、検索結果を表示するルート"""
    query = request.form.get('query')
    if not query:
        return render_template_string(ERROR_TEMPLATE, message="検索キーワードが必要です。")

    try:
        response = requests.get(f"{INVIDIOUS_URL}/api/v1/search", params={"q": query})
        response.raise_for_status()
        data = response.json()
        videos = [item for item in data if item["type"] == "video"]
        return render_template_string(SEARCH_RESULTS_TEMPLATE, videos=videos)
    except requests.exceptions.RequestException as e:
        return render_template_string(ERROR_TEMPLATE, message=f"APIリクエストに失敗しました: {e}")
    except ValueError:
        return render_template_string(ERROR_TEMPLATE, message="APIからのレスポンスが無効です。")

@app.route('/video/<video_id>')
def video_view(video_id):
    """動画IDに基づいて動画詳細と関連動画を表示するルート"""
    try:
        # 動画詳細の取得
        response = requests.get(f"{INVIDIOUS_URL}/api/v1/videos/{video_id}")
        response.raise_for_status()
        video = response.json()

        # 最高解像度のフォーマットを選択
        formats = video.get("formats", [])
        if not formats:
            return render_template_string(ERROR_TEMPLATE, message="利用可能な動画フォーマットがありません。")

        def get_resolution_num(resolution):
            if resolution.endswith("p"):
                return int(resolution[:-1])
            elif resolution.endswith("k"):
                return int(resolution[:-1]) * 1000
            return 0

        sorted_formats = sorted(formats, key=lambda f: get_resolution_num(f.get("resolution", "0p")), reverse=True)
        best_format = sorted_formats[0]

        # 関連動画の提案を取得
        suggestions_response = requests.get(f"{INVIDIOUS_URL}/api/v1/suggestions/{video_id}")
        suggestions_response.raise_for_status()
        suggestions = suggestions_response.json().get("suggestions", [])

        return render_template_string(VIDEO_TEMPLATE, video=video, format=best_format, suggestions=suggestions)
    except requests.exceptions.RequestException as e:
        return render_template_string(ERROR_TEMPLATE, message=f"APIリクエストに失敗しました: {e}")
    except ValueError:
        return render_template_string(ERROR_TEMPLATE, message="APIからのレスポンスが無効です。")

if __name__ == '__main__':
    app.run(debug=True, port=8025)