import os
import secrets
from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = './files'
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 * 1024  # 1GB

def load_passwords():
    """パスワード情報を読み込む"""
    passwords = {}
    if os.path.exists('pass.txt'):
        with open('pass.txt', 'r') as f:
            for line in f:
                parts = line.strip().split(':')
                if len(parts) == 2:
                    filename, password = parts
                    passwords[filename] = password
    return passwords

def save_password(filename, password):
    """パスワード情報を保存する"""
    with open('pass.txt', 'a') as f:
        f.write(f'{filename}:{password}\n')

def generate_link():
  """ファイル共有用のリンクを生成する"""
  return secrets.token_urlsafe(16)

@app.route('/', methods=['GET', 'POST'])
def index():
    """ファイルのアップロードと一覧表示"""
    passwords = load_passwords()
    error = None
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(file_path):
                error = '同じ名前のファイルがすでに存在します。別のファイル名を試してください。'
            else:
                file.save(file_path)

                password = request.form.get('password')
                if password:
                    save_password(filename, password)

                link = generate_link()
                return render_template('index.html', files=os.listdir(app.config['UPLOAD_FOLDER']),link=link, error=None)

    return render_template('index.html', files=os.listdir(app.config['UPLOAD_FOLDER']),link='', error=error)

@app.route('/files/<filename>', methods=['GET', 'POST'])
def download(filename):
    """ファイルのダウンロード"""
    passwords = load_passwords()
    password = passwords.get(filename)
    if password:
        if request.method == 'POST':
            input_password = request.form.get('password')
            if input_password == password:
                return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
            else:
                return render_template('password.html', filename=filename, error='パスワードが違います')
        else:
            return render_template('password.html', filename=filename, error=None)
    else:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/del/<filename>')
def delete(filename):
    """ファイルの削除"""
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        passwords = load_passwords()
        if filename in passwords:
            del passwords[filename]
            with open('pass.txt', 'w') as f:
                for file, pwd in passwords.items():
                    f.write(f'{file}:{pwd}\n')

        return redirect(url_for('index'))
    else:
        return 'ファイルが見つかりません'

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=4649)
