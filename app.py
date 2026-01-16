import os
import uuid
import subprocess
import sqlite3
import json
import time
from flask import Flask, render_template, request, redirect, url_for, session, g

app = Flask(__name__)
app.secret_key = 'justus_secret_key'

# --- 路徑設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'cpp_oj.db')
TEMP_DIR = os.path.join(BASE_DIR, 'temp_code')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ADMIN_PASSWORD = 'Xiang520'

# 頻率限制 (秒)
RATE_LIMIT_SECONDS = 15

if not os.path.exists(TEMP_DIR): os.makedirs(TEMP_DIR)
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)

# --- 資料庫連線 ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        # 題目表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS problems (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                image_filename TEXT,
                samples TEXT NOT NULL,
                test_cases TEXT NOT NULL
            )
        ''')
        # [新增] 提交紀錄表 (用來存 IP 和上次提交時間)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS submission_logs (
                ip TEXT PRIMARY KEY,
                last_submit_time REAL
            )
        ''')
        db.commit()

# --- 輔助函式 ---
def is_safe_code(code):
    code_lower = code.lower()
    forbidden_keywords = ['system(', 'rm -rf', 'execl', 'execv', 'popen', '/etc/passwd']
    for keyword in forbidden_keywords:
        if keyword in code_lower: return False
    return True

def normalize_output(text):
    if not text: return ""
    return text.strip().replace('\r\n', '\n')

# --- 路由 ---

@app.route('/')
def home():
    db = get_db()
    problems = db.execute('SELECT id, title, description, image_filename FROM problems').fetchall()
    return render_template('home.html', problems=problems)

@app.route('/problem/<int:problem_id>', methods=['GET', 'POST'])
def problem_view(problem_id):
    db = get_db()
    
    current_problem = db.execute('SELECT * FROM problems WHERE id = ?', (problem_id,)).fetchone()
    if not current_problem:
        return redirect(url_for('home'))

    problems = db.execute('SELECT id, title FROM problems').fetchall()

    output = ""
    code_content = ""
    status = None
    problem_samples = []

    try:
        problem_samples = json.loads(current_problem['samples'])
    except:
        problem_samples = []

    if request.method == 'POST' and 'submit_code' in request.form:
        # --- [修改] 使用資料庫進行頻率檢查 ---
        client_ip = request.remote_addr
        current_time = time.time()
        
        # 1. 從資料庫查詢該 IP 上次的時間
        log_row = db.execute('SELECT last_submit_time FROM submission_logs WHERE ip = ?', (client_ip,)).fetchone()
        last_submit_time = log_row['last_submit_time'] if log_row else 0
        
        time_diff = current_time - last_submit_time
        
        # 讀取內容 (保留使用者輸入)
        file = request.files.get('file')
        text_code = request.form.get('code')
        if file and file.filename != '':
            code_content = file.read().decode('utf-8', errors='ignore')
        elif text_code:
            code_content = text_code

        # 2. 檢查時間差
        if time_diff < RATE_LIMIT_SECONDS:
            wait_time = int(RATE_LIMIT_SECONDS - time_diff)
            output = f"🚫 動作太快了！請等待 {wait_time} 秒後再試。"
        else:
            # 3. [重要] 更新資料庫時間 (使用 REPLACE INTO 語法，如果 IP 存在就更新，不存在就新增)
            db.execute('INSERT OR REPLACE INTO submission_logs (ip, last_submit_time) VALUES (?, ?)', 
                       (client_ip, current_time))
            db.commit() # 務必提交變更
            
            if not code_content:
                output = "錯誤：請提供程式碼"
            else:
                # --- 原本的編譯與執行邏輯 (保持不變) ---
                if not is_safe_code(code_content):
                    output = "別鬧了！禁止使用系統指令或危險操作。"
                    status = "Dangerous"
                else:
                    unique_id = str(uuid.uuid4())
                    source_filename = os.path.join(TEMP_DIR, f"{unique_id}.cpp")
                    exec_filename = os.path.join(TEMP_DIR, f"{unique_id}.out")
                    input_filename = os.path.join(TEMP_DIR, f"{unique_id}.in")

                    try:
                        with open(source_filename, 'w') as f:
                            f.write(code_content)
                        
                        compile_env = os.environ.copy()
                        compile_env['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'

                        compile_process = subprocess.run(
                            ['/usr/bin/g++', source_filename, '-o', exec_filename],
                            capture_output=True, text=True, env=compile_env
                        )

                        if compile_process.returncode != 0:
                            output = f"編譯錯誤:\n{compile_process.stderr}"
                            status = "CE"
                        else:
                            try:
                                test_cases = json.loads(current_problem['test_cases'])
                            except:
                                test_cases = []
                            
                            all_passed = True
                            if not test_cases:
                                status = "WA"
                                output = "錯誤：本題尚未設定測試資料。"
                                all_passed = False

                            for i, case in enumerate(test_cases):
                                with open(input_filename, 'w') as f:
                                    f.write(case['in'])
                                try:
                                    with open(input_filename, 'r') as infile:
                                        run_process = subprocess.run(
                                            [exec_filename], stdin=infile, capture_output=True, text=True, timeout=2
                                        )
                                    if run_process.stderr:
                                        status = "RE"
                                        output = f"執行錯誤 (Case {i+1}):\n{run_process.stderr}"
                                        all_passed = False
                                        break
                                    user_out = normalize_output(run_process.stdout)
                                    std_out = normalize_output(case['out'])
                                    if user_out != std_out:
                                        status = "WA"
                                        output = f"答案錯誤 (WA) - Case {i+1} 失敗。\n您的輸出:\n{user_out}"
                                        all_passed = False
                                        break
                                except subprocess.TimeoutExpired:
                                    status = "TLE"
                                    output = f"執行逾時 (TLE) - Case {i+1}"
                                    all_passed = False
                                    break
                            
                            if all_passed:
                                status = "AC"
                                output = "恭喜！所有測試資料皆通過 (All Test Cases Passed)。"
                    except Exception as e:
                        output = f"系統錯誤: {str(e)}"
                    finally:
                        for f in [source_filename, exec_filename, input_filename]:
                            if os.path.exists(f): os.remove(f)

    return render_template('index.html', problems=problems, current_problem=current_problem, 
                           problem_samples=problem_samples, output=output, code=code_content, status=status)

@app.route('/edit/<int:problem_id>', methods=['GET', 'POST'])
def edit_problem(problem_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    db = get_db()
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        
        image = request.files.get('image')
        image_update_sql = ""
        image_param = []
        if image and image.filename != '':
            ext = os.path.splitext(image.filename)[1]
            new_filename = f"img_{uuid.uuid4().hex}{ext}"
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
            image_update_sql = ", image_filename = ?"
            image_param = [new_filename]

        s_inputs = request.form.getlist('sample_input[]')
        s_outputs = request.form.getlist('sample_output[]')
        samples_list = []
        for i in range(len(s_inputs)):
            if s_inputs[i].strip() or s_outputs[i].strip():
                samples_list.append({"in": s_inputs[i], "out": s_outputs[i]})
        samples_json = json.dumps(samples_list)

        t_inputs = request.form.getlist('test_input[]')
        t_outputs = request.form.getlist('test_output[]')
        cases_list = []
        for i in range(len(t_inputs)):
            if t_inputs[i].strip() or t_outputs[i].strip():
                cases_list.append({"in": t_inputs[i], "out": t_outputs[i]})
        test_cases_json = json.dumps(cases_list)

        sql = f'''
            UPDATE problems 
            SET title = ?, description = ?, samples = ?, test_cases = ? {image_update_sql}
            WHERE id = ?
        '''
        params = [title, description, samples_json, test_cases_json] + image_param + [problem_id]
        
        db.execute(sql, params)
        db.commit()
        return redirect(url_for('admin'))

    problem = db.execute('SELECT * FROM problems WHERE id = ?', (problem_id,)).fetchone()
    if not problem: return "題目不存在"

    try: samples = json.loads(problem['samples'])
    except: samples = []
    
    try: test_cases = json.loads(problem['test_cases'])
    except: test_cases = []

    return render_template('edit.html', problem=problem, samples=samples, test_cases=test_cases)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form['password'] == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin'))
        else:
            error = '密碼錯誤'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('logged_in'): return redirect(url_for('login'))
    db = get_db()
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        
        image = request.files.get('image')
        image_filename = None
        if image and image.filename != '':
            ext = os.path.splitext(image.filename)[1]
            new_filename = f"img_{uuid.uuid4().hex}{ext}"
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
            image_filename = new_filename

        s_inputs = request.form.getlist('sample_input[]')
        s_outputs = request.form.getlist('sample_output[]')
        samples_list = []
        for i in range(len(s_inputs)):
            if s_inputs[i].strip() or s_outputs[i].strip():
                samples_list.append({"in": s_inputs[i], "out": s_outputs[i]})
        samples_json = json.dumps(samples_list)

        t_inputs = request.form.getlist('test_input[]')
        t_outputs = request.form.getlist('test_output[]')
        cases_list = []
        for i in range(len(t_inputs)):
            if t_inputs[i].strip() or t_outputs[i].strip():
                cases_list.append({"in": t_inputs[i], "out": t_outputs[i]})
        test_cases_json = json.dumps(cases_list)

        db.execute('''
            INSERT INTO problems (title, description, image_filename, samples, test_cases) 
            VALUES (?, ?, ?, ?, ?)
        ''', (title, description, image_filename, samples_json, test_cases_json))
        db.commit()
        return redirect(url_for('admin'))

    problems = db.execute('SELECT * FROM problems ORDER BY id DESC').fetchall()
    return render_template('admin.html', problems=problems)

@app.route('/delete/<int:problem_id>')
def delete_problem(problem_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    db = get_db()
    problem = db.execute('SELECT image_filename FROM problems WHERE id = ?', (problem_id,)).fetchone()
    if problem and problem['image_filename']:
        img_path = os.path.join(app.config['UPLOAD_FOLDER'], problem['image_filename'])
        if os.path.exists(img_path): os.remove(img_path)
    db.execute('DELETE FROM problems WHERE id = ?', (problem_id,))
    db.commit()
    return redirect(url_for('admin'))

with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)