# ultra_file.py
import os
import mimetypes
from flask import Flask, request, render_template, send_file, jsonify
from werkzeug.utils import secure_filename
import magic

app = Flask(__name__)

# 設定
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'zip', 'rar', 'mp3', 'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv', 'wav', 'ogg', 'bmp', 'tiff', 'svg', 'html', 'css', 'js', 'py', 'java', 'cpp', 'c', 'json', 'xml', 'rtf', 'odt', 'ods', 'odp', 'epub', 'mobi', 'azw', 'fb2', 'djvu', 'psd', 'ai', 'indd', 'sketch', 'fig', 'xcf', 'raw', 'nef', 'cr2', 'orf', 'sr2', '3fr', 'ari', 'arw', 'bay', 'cap', 'data', 'dcs', 'dcr', 'drf', 'eip', 'erf', 'fff', 'iiq', 'k25', 'kdc', 'mdc', 'mef', 'mos', 'mrw', 'nef', 'nrw', 'obm', 'orf', 'pef', 'ptx', 'pxn', 'r3d', 'raf', 'raw', 'rw2', 'rwl', 'rwz', 'sr2', 'srf', 'srw', 'x3f'}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# ファイルの種類を判定する関数
def get_file_type(file_path):
    try:
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type:
            return mime_type
        # magicライブラリを使ってファイルタイプを判定
        file_type = magic.from_file(file_path, mime=True)
        return file_type
    except Exception as e:
        print(f"Error detecting file type: {e}")
        return "unknown"

# ファイルの拡張子を取得する関数
def get_file_extension(file_path):
    _, extension = os.path.splitext(file_path)
    return extension.lower()[1:]  # 拡張子を小文字に変換し、ドットを削除

# アップロードされたファイルの拡張子を確認
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ファイルを変換する関数（ここでは例として、テキストファイルをHTMLに変換）
def convert_file(input_path, output_path, input_format, output_format):
    try:
        # 変換処理
        if input_format == 'txt' and output_format == 'html':
            with open(input_path, 'r', encoding='utf-8') as f_in:
                content = f_in.read()
            with open(output_path, 'w', encoding='utf-8') as f_out:
                f_out.write(f'<html><body><pre>{content}</pre></body></html>')
        else:
            # 他の変換処理をここに追加
            raise NotImplementedError("この形式の変換はまだ実装されていません")
    except Exception as e:
        print(f"Error converting file: {e}")
        raise

# ファイルをアップロードして変換するエンドポイント
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'ファイルが選択されていません'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'ファイルが選択されていません'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(input_path)
        
        # ファイルの種類を取得
        file_type = get_file_type(input_path)
        file_extension = get_file_extension(input_path)
        
        # 変換先のフォーマットを指定（ここでは例として、テキストファイルをHTMLに変換）
        if file_extension == 'txt':
            output_format = 'html'
            output_filename = f"{os.path.splitext(filename)[0]}.{output_format}"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            try:
                convert_file(input_path, output_path, file_extension, output_format)
                
                # 元のファイルを削除
                os.remove(input_path)
                
                return jsonify({
                    'message': 'ファイルが正常に変換されました',
                    'download_url': f'/download/{output_filename}'
                })
            except NotImplementedError:
                return jsonify({'error': 'この形式の変換はまだ実装されていません'}), 400
            except Exception as e:
                return jsonify({'error': f'変換エラー: {str(e)}'}), 500
        else:
            # 変換がサポートされていない場合は、そのままファイルを返す
            return jsonify({
                'message': 'この形式の変換はまだ実装されていません',
                'file_type': file_type,
                'original_filename': filename
            })
    else:
        return jsonify({'error': '許可されていないファイル形式です'}), 400

# ファイルをダウンロードするエンドポイント
@app.route('/download/<filename>')
def download_file(filename):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            return jsonify({'error': 'ファイルが見つかりません'}), 404
    except Exception as e:
        return jsonify({'error': f'ダウンロードエラー: {str(e)}'}), 500

# メインページを表示するエンドポイント
@app.route('/')
def index():
    return render_template('index.html')

# アプリケーションの起動
if __name__ == '__main__':
    # アップロードフォルダが存在しない場合は作成
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
