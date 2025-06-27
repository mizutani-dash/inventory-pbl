import os
import sqlite3
import csv
import codecs
from flask import Flask, request, render_template, redirect, url_for, jsonify
from werkzeug.utils import secure_filename

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
    """データベースを初期化し、テーブルを作成します。"""
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
    """CSVファイルをアップロードして処理します。"""
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
            data_rows = []
            try:
                # BOM付きUTF-8に対応するため 'utf-8-sig' を使用
                with open(filepath, 'r', encoding='utf-8-sig', newline='') as f:
                    reader = csv.reader(f)
                    data_rows = list(reader)
            except UnicodeDecodeError:
                # UTF-8で失敗した場合、Shift-JISで試す
                with open(filepath, 'r', encoding='shift_jis', newline='') as f:
                    reader = csv.reader(f)
                    data_rows = list(reader)

            if not data_rows:
                return jsonify({'error': 'CSVファイルが空か、読み取れませんでした'}), 400

            header = data_rows[0]
            # 必要なカラムのインデックスを取得
            try:
                date_idx = header.index('日付')
                product_name_idx = header.index('商品名')
                units_sold_idx = header.index('販売本数')
            except ValueError as e:
                return jsonify({'error': f'必要なカラムが見つかりません: {e}。CSVには「日付」「商品名」「販売本数」のヘッダーが必要です。'}), 400

            db = get_db()
            with db:
                # ヘッダー行を除いてデータを処理
                for row in data_rows[1:]:
                    if not row: continue  # 空行をスキップ
                    try:
                        date = row[date_idx]
                        product_name = row[product_name_idx]
                        units_sold = int(row[units_sold_idx])
                        db.execute(
                            'INSERT INTO sales (date, product_name, units_sold) VALUES (?, ?, ?)',
                            (date, product_name, units_sold)
                        )
                    except (ValueError, IndexError):
                        # データ形式が不正な行はスキップ
                        continue
            db.close()
            return jsonify({'success': 'ファイルが正常に処理されました'}), 200

        except Exception as e:
            return jsonify({'error': f'ファイルの処理中にエラーが発生しました: {e}'}), 500
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

if __name__ == '__main__':
    app.run(debug=True)
