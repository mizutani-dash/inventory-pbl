import os
import sqlite3
import pandas as pd
from datetime import datetime
from flask import Flask, request, render_template, redirect, url_for, jsonify, send_file
from werkzeug.utils import secure_filename
import hashlib
import traceback
import io
from openpyxl import load_workbook
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['DATABASE'] = 'database.db'
app.config['ALLOWED_EXTENSIONS'] = {'csv'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def connect_sheets():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    json_content = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    creds_dict = json.loads(json_content)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open('【開発用】シードル出庫台帳')
    return sheet.worksheet('出庫情報'), sheet.worksheet('出庫詳細')


def get_db():
    db = sqlite3.connect(app.config['DATABASE'])
    db.row_factory = sqlite3.Row
    return db

def init_db():
    """データベースを初期化し、必要に応じてスキーマを更新します。"""
    with app.app_context():
        db = get_db()
        with db:
            db.execute('''
                CREATE TABLE IF NOT EXISTS alcohol_sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    sales_count INTEGER NOT NULL,
                    source_filename TEXT NOT NULL
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
            try:
                cur = db.cursor()
                cur.execute("PRAGMA table_info(alcohol_sales)")
                columns = [row[1] for row in cur.fetchall()]
                if 'source_filename' not in columns:
                    print("Migrating database schema: Adding 'source_filename' column.")
                    db.execute("ALTER TABLE alcohol_sales ADD COLUMN source_filename TEXT NOT NULL DEFAULT 'unknown'")
            except Exception as e:
                print(f"Could not perform schema migration: {e}")
        db.close()

init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def calculate_file_hash(filepath):
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        hasher.update(f.read())
    return hasher.hexdigest()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
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
            file_hash = calculate_file_hash(filepath)
            db = get_db()
            cur = db.execute('SELECT * FROM upload_log WHERE file_hash = ?', (file_hash,))
            existing = cur.fetchone()
            db.close()

            if existing:
                return jsonify({
                    'status': 'confirm',
                    'message': '同じ内容のファイルが既にアップロードされています。上書きして処理を続行しますか？ (既存のデータは削除されます)',
                    'filename': filename,
                    'file_hash': file_hash
                })

            return process_and_store_csv(filepath, filename, file_hash)

        except Exception as e:
            print(f"!!! An error occurred during upload: {e} !!!")
            traceback.print_exc()
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({'error': f'ファイル処理中にエラーが発生しました: {e}'}), 500
    else:
        return jsonify({'error': '許可されていないファイル形式です'}), 400

@app.route('/confirm_upload', methods=['POST'])
def confirm_upload():
    """重複確認後、古いデータを削除してからアップロード処理を続行します。"""
    filename = request.form['filename']
    file_hash = request.form['file_hash']
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    try:
        db = get_db()
        with db:
            print(f"[INFO] Deleting old records for file: {filename}")
            db.execute('DELETE FROM alcohol_sales WHERE source_filename = ?', (filename,))
        db.close()
        
        return process_and_store_csv(filepath, filename, file_hash)
        
    except Exception as e:
        print(f"!!! An error occurred during re-processing: {e} !!!")
        traceback.print_exc()
        return jsonify({'error': f'再処理中にエラーが発生しました: {e}'}), 500

from openpyxl import load_workbook

def process_and_store_csv(filepath, filename, file_hash):
    """CSVを解析し、「お酒類」のデータをDBとExcelに登録します。"""
    try:
        date_str = os.path.basename(filename).split('-')[0]
        sale_date = datetime.strptime(date_str, '%Y%m%d').strftime('%Y-%m-%d')
        print(f"\n--- Processing file: {filename} for date: {sale_date} ---")

        try:
            df = pd.read_csv(filepath, header=None, encoding='shift-jis')
        except Exception:
            df = pd.read_csv(filepath, header=None, encoding='utf-8')
        
        print(f"[DEBUG] CSV loaded. Shape: {df.shape}")
        if 1 in df.columns:
            unique_categories = df[1].astype(str).str.strip().unique()
            print(f"[DEBUG] Unique categories in column B: {unique_categories}")
        else:
            return jsonify({'error': 'CSVファイルにカテゴリ列（B列）が見つかりません。'}), 500

        df_filtered = df[df[1].astype(str).str.strip() == 'お酒類'].copy()
        if df_filtered.empty:
            return jsonify({'success': 'ファイルは処理されましたが、「お酒類」のデータは見つかりませんでした。'}), 200

        if 0 not in df_filtered.columns or 7 not in df_filtered.columns:
            return jsonify({'error': '必要な列（A列またはH列）が見つかりません。'}), 500

        result_df = df_filtered[[0, 7]].copy()
        result_df.columns = ['product_name', 'sales_count']
        result_df['sales_count'] = pd.to_numeric(result_df['sales_count'], errors='coerce').fillna(0).astype(int)
        result_df['date'] = sale_date
        result_df['source_filename'] = filename

        product_name_mapping = {
            "シードル辛口フル　2180円": "シードル辛口2025／フル",
            "シードル甘口ハーフ　1250円": "シードル甘口2025／ハーフ",
            "シードル辛口ハーフ　1250円": "シードル辛口2025／ハーフ",
            "シードル　低アルコール　2180円": "低アルコール2025／フル",
            "シードル甘口フル　2180円": "シードル甘口2025／フル",
            "洋梨スパークリング　フル　2600円": "洋梨／フル2025",
            "洋梨スパークリング　ハーフ　1500円": "洋梨／ハーフ2025",
            "ワインハーフボトル1500円": "ワイン／ハーフ2025",
            "ワインフルボトル2600円": "ワイン／フル2025",
            "シナノブレンド甘口　1250円": "シナノブレンド甘口2025",
            "シナノブレンド辛口　1250円": "シナノブレンド辛口2025",
            "シードル【フル】3本セット　6500円": "シードル3本セット2025／フル"
        }

        result_df['product_name'] = result_df['product_name'].astype(str).str.strip().map(product_name_mapping)

        # マッピングされなかった商品は除外
        result_df.dropna(subset=['product_name'], inplace=True)

        print("[DEBUG] Data to be inserted (first 5 rows):")
        print(result_df.head().to_string())

        conn = get_db()
        with conn:
            result_df.to_sql('alcohol_sales', conn, if_exists='append', index=False)
            conn.execute(
                'INSERT OR IGNORE INTO upload_log (filename, file_hash) VALUES (?, ?)',
                (filename, file_hash)
            )
        conn.close()

        # Google スプレッドシートへの追記
        try:
            sheet1, sheet2 = connect_sheets()
            existing_ids = sheet1.col_values(1)[1:]  # 出庫ID列（ヘッダー除く）
            today = datetime.strptime(sale_date, '%Y-%m-%d').strftime('%y%m%d')

            # 使用済み番号セット
            used_numbers = set()
            for id_ in existing_ids:
                match = re.match(rf'^{today}-(\d+)$', str(id_))
                if match:
                    used_numbers.add(int(match.group(1)))

            # 出庫IDジェネレーター定義
            def get_next_shukko_id(start=1):
                num = start
                while True:
                    if num not in used_numbers:
                        used_numbers.add(num)
                        yield f'{today}-{num:03d}'
                    num += 1

            id_generator = get_next_shukko_id()
            shukko_ids = []

            for _, row in result_df.iterrows():
                shukko_id = next(id_generator)
                shukko_ids.append(shukko_id)

            # Google Sheets に書き込む
            write_to_google_sheets(result_df, shukko_ids)
            print("[INFO] Googleスプレッドシートに出庫データを追加しました。")

        except Exception as e:
            print(f"[ERROR] Google Sheetsへの書き込みに失敗しました: {e}")

        print("--- Processing finished successfully ---")
        return jsonify({'success': 'ファイルが正常に処理され、データベースおよびスプレッドシートに登録されました。'}), 200

    except Exception as e:
        print(f"!!! An error occurred: {e} !!!")
        traceback.print_exc()
        return jsonify({'error': f'CSV処理中に予期せぬエラーが発生しました: {e}'}), 500


@app.route('/data')
def show_data():
    db = get_db()
    entries = db.execute('SELECT id, date, product_name, sales_count FROM alcohol_sales ORDER BY date DESC, id DESC').fetchall()
    db.close()
    return render_template('data.html', entries=entries)

@app.route('/delete/<int:id>', methods=['POST'])
def delete_entry(id):
    db = get_db()
    with db:
        db.execute('DELETE FROM alcohol_sales WHERE id = ?', (id,))
    db.close()
    return redirect(url_for('show_data'))

@app.route('/delete_all', methods=['POST'])
def delete_all_entries():
    db = get_db()
    with db:
        db.execute('DELETE FROM alcohol_sales')
        db.execute('DELETE FROM upload_log')
    db.close()
    return redirect(url_for('show_data'))

@app.route('/export')
def export_excel():
    """データベースのデータをExcelファイルとしてエクスポートします。"""
    try:
        db = get_db()
        df = pd.read_sql_query("SELECT date, product_name, sales_count FROM alcohol_sales ORDER BY date DESC, id DESC", db)
        db.close()

        if df.empty:
            return redirect(url_for('show_data'))

        df.rename(columns={
            'date': '日付',
            'product_name': '商品名',
            'sales_count': '販売本数'
        }, inplace=True)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='アルコール販売実績')
        output.seek(0)

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='alcohol_sales_data.xlsx'
        )
    except Exception as e:
        print(f"!!! Excelエクスポート中にエラーが発生: {e} !!!")
        traceback.print_exc()
        return redirect(url_for('show_data'))

def write_to_google_sheets(result_df, shukko_ids):
    try:
        # シートに接続
        sheet1, sheet2 = connect_sheets()

        for i, (_, row) in enumerate(result_df.iterrows()):
            shukko_id = shukko_ids[i]

            # 出庫情報シート：出庫ID・日付・出庫先・取引先・担当者
            sheet1.append_row([
                shukko_id,
                row['date'],
                '店頭販売',
                '',
                '北沢'
            ])

            # 出庫詳細シート：出庫ID・商品名・数量
            sheet2.append_row([
                shukko_id,
                row['product_name'],
                row['sales_count']
            ])

        print("[INFO] Googleスプレッドシートにデータを追加しました。")
    except Exception as e:
        print(f"[ERROR] Googleスプレッドシートへの書き込みに失敗しました: {e}")




if __name__ == '__main__':
    app.run(debug=True)
