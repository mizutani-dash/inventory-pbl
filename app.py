import os
import sqlite3
import csv
import codecs
from flask import Flask, request, render_template, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
import hashlib

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['DATABASE'] = 'database.db'
app.config['ALLOWED_EXTENSIONS'] = {'csv'}

# Ensure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def get_db():
    """データベース接続を取得します。"""
    db = sqlite3.connect(app.config['DATABASE'])
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with app.app_context():
        db = get_db()
        with db:
            db.execute('''
                CREATE TABLE IF NOT EXISTS sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    units_sold INTEGER NOT NULL
                )
            ''')
            db.execute('''
                CREATE TABLE IF NOT EXISTS upload_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    file_hash TEXT UNIQUE NOT NULL,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        db.close()


init_db() # アプリケーション起動時にDBを初期化

def allowed_file(filename):
    """許可されたファイル形式かチェックします。"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    """メインページを表示します。"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """CSVファイルをアップロードして処理します（重複ハッシュ確認付き）"""
    if 'file' not in request.files:
        return jsonify({'error': 'ファイルがありません'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'ファイルが選択されていません'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            # 1. ファイルのハッシュ値を計算
            file_hash = calculate_file_hash(filepath)

            # 2. 過去に同じファイルがアップロードされたか確認
            db = get_db()
            cur = db.execute('SELECT * FROM upload_log WHERE file_hash = ?', (file_hash,))
            existing = cur.fetchone()
            db.close()

            if existing:
                # → 確認を求めるJSONを返す
                return jsonify({
                    'status': 'confirm',
                    'message': '同じ内容のファイルが既にアップロードされています。上書きして処理を続行しますか？',
                    'filename': filename,
                    'file_hash': file_hash
                })

            # 3. ハッシュが新しい場合は、そのまま処理
            return process_csv(filepath, filename, file_hash)

        except Exception as e:
            return jsonify({'error': f'ファイル処理中に予期せぬエラーが発生しました: {e}'}), 500

    else:
        return jsonify({'error': '許可されていないファイル形式です'}), 400


@app.route('/data')
def show_data():
    """データベースのデータを表示します。"""
    db = get_db()
    cur = db.execute('SELECT date, product_name, units_sold FROM sales ORDER BY date DESC')
    entries = cur.fetchall()
    db.close()
    return render_template('data.html', entries=entries)

def calculate_file_hash(filepath):
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        hasher.update(f.read())
    return hasher.hexdigest()

@app.route('/confirm_upload', methods=['POST'])
def confirm_upload():
    filename = request.form['filename']
    file_hash = request.form['file_hash']
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    return process_csv(filepath, filename, file_hash)

def process_csv(filepath, filename, file_hash):
    """CSVを解析してDBに登録し、upload_log にハッシュを記録する"""
    try:
        data_rows = []
        try:
            with open(filepath, 'r', encoding='utf-8-sig', newline='') as f:
                reader = csv.reader(f)
                data_rows = list(reader)
        except UnicodeDecodeError:
            with open(filepath, 'r', encoding='shift_jis', newline='') as f:
                reader = csv.reader(f)
                data_rows = list(reader)

        if not data_rows:
            return jsonify({'error': 'CSVファイルが空、または読み取れません'}), 400

        header = data_rows[0]
        try:
            date_idx = header.index('日付')
            product_name_idx = header.index('商品名')
            units_sold_idx = header.index('販売本数')
        except ValueError as e:
            return jsonify({'error': f'必要なカラムが見つかりません: {e}'}), 400

        db = get_db()
        with db:
            for row in data_rows[1:]:
                if not row:
                    continue
                try:
                    date = row[date_idx]
                    product_name = row[product_name_idx]
                    units_sold = int(row[units_sold_idx])
                    db.execute(
                        'INSERT INTO sales (date, product_name, units_sold) VALUES (?, ?, ?)',
                        (date, product_name, units_sold)
                    )
                except (ValueError, IndexError):
                    continue
            # upload_logにも記録
            db.execute(
                'INSERT OR IGNORE INTO upload_log (filename, file_hash) VALUES (?, ?)',
                (filename, file_hash)
            )
        db.close()
        return jsonify({'success': 'ファイルが正常に処理されました'}), 200

    except Exception as e:
        return jsonify({'error': f'CSV処理中にエラーが発生しました: {e}'}), 500



if __name__ == '__main__':
    app.run(debug=True)
