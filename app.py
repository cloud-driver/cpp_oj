import os
import uuid
import sqlite3
import json
import time
import requests
import docker
from docker.errors import ContainerError
from docker.types import Ulimit
from flask import Flask, render_template, request, redirect, url_for, session, g, send_from_directory, make_response, flash
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

# 優先載入環境變數
load_dotenv()

app = Flask(__name__)

# --- 設定區 ---
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
OLLAMA_API_URL = os.getenv('OLLAMA_API_URL', 'http://localhost:11434/api/generate')

# 路徑設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'cpp_oj.db')
TEMP_DIR = os.path.join(BASE_DIR, 'temp_code')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/uploads')
LOG_FILE = os.path.join(BASE_DIR, 'oj_events.log')
SECCOMP_PROFILE_PATH = os.path.join(BASE_DIR, 'oj_seccomp.json')

# 系統參數
RATE_LIMIT_SECONDS = 15
AI_RATE_LIMIT_SECONDS = 30
AI_MODEL = "gemini-3-flash-preview"
DOCKER_IMAGE = 'gcc:latest'

# [注意] 請確保 Host 機器上存在此 UID/GID，或根據實際情況調整
OJ_RUNNER_UID = "999" 
OJ_RUNNER_GID = "986"

# Flask Config
app.config['SESSION_COOKIE_SECURE'] = True 
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default-unsafe-key')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config['CSRF_TRUSTED_ORIGINS'] = ['https://project.hasaki.idv.tw']

csrf = CSRFProtect(app)

# 初始化 Docker Client
docker_client = None
try:
    docker_client = docker.from_env()
except Exception as e:
    print(f"嚴重警告：無法連線到 Docker Daemon。評測功能將無法使用。\n錯誤訊息: {e}")

# 建立必要目錄
if not os.path.exists(TEMP_DIR): os.makedirs(TEMP_DIR)
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)

# --- Helper Functions ---

def get_real_ip():
    if request.headers.getlist("CF-Connecting-IP"):
        return request.headers.get("CF-Connecting-IP")
    return request.remote_addr

def write_log(event_message):
    ip = get_real_ip()
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    log_content = f"{ip} : {current_time} : {event_message}"
    print(log_content)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_content + '\n')
    except: pass

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None: db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # 1. 題目表
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

        # 2. 使用者表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user', 
                created_at REAL
            )
        ''')

        # 3. 提交紀錄表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                problem_id INTEGER,
                status TEXT, -- AC, WA, TLE, CE, RE
                code TEXT,
                timestamp REAL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(problem_id) REFERENCES problems(id)
            )
        ''')

        # 4. Log 表
        cursor.execute('CREATE TABLE IF NOT EXISTS submission_logs (ip TEXT PRIMARY KEY, last_submit_time REAL)')
        cursor.execute('CREATE TABLE IF NOT EXISTS ai_logs (ip TEXT PRIMARY KEY, last_request_time REAL)')
        
        # 預先建立管理員帳號
        admin_user = cursor.execute('SELECT * FROM users WHERE username = ?', (ADMIN_USERNAME,)).fetchone()
        if not admin_user:
            hashed_pw = generate_password_hash(ADMIN_PASSWORD)
            cursor.execute('INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)', 
                           (ADMIN_USERNAME, hashed_pw, 'admin', time.time()))
            print(f"系統自動建立管理員帳號: {ADMIN_USERNAME}")

        db.commit()

def normalize_output(text):
    if not text: return ""
    return text.strip().replace('\r\n', '\n')

# --- 核心邏輯：編譯與執行 ---

def compile_code(source_filename, exec_filename):
    if not docker_client: return False, "Docker 未啟動"
    
    src_name = os.path.basename(source_filename)
    exec_name = os.path.basename(exec_filename)
    volumes = {TEMP_DIR: {'bind': '/app', 'mode': 'rw'}}

    try:
        docker_client.containers.run(
            image=DOCKER_IMAGE,
            command=f"g++ {src_name} -o {exec_name}",
            volumes=volumes,
            working_dir='/app',
            remove=True,
            network_disabled=True,
            mem_limit='256m'
        )
        return True, ""
    except ContainerError as e:
        return False, e.stderr.decode('utf-8', errors='ignore')
    except Exception as e:
        return False, str(e)

def execute_code(exec_filename, input_data):
    if not docker_client: return False, "Docker 未啟動"

    unique_id = uuid.uuid4().hex
    temp_input_path = os.path.join(TEMP_DIR, f"{unique_id}.in")
    
    with open(temp_input_path, 'w') as f:
        f.write(input_data)
        
    exec_name = os.path.basename(exec_filename)
    in_name = os.path.basename(temp_input_path)
    volumes = {TEMP_DIR: {'bind': '/app', 'mode': 'rw'}}

    try:
        container = docker_client.containers.run(
            image=DOCKER_IMAGE,
            command=f"sh -c './{exec_name} < {in_name}'",
            volumes=volumes,
            working_dir='/app',
            detach=True,
            user=f"{OJ_RUNNER_UID}:{OJ_RUNNER_GID}", 
            ulimits=[Ulimit(name='nproc', soft=20, hard=20)],
            pids_limit=30,
            security_opt=['no-new-privileges'],
            network_disabled=True,
            mem_limit='128m',
            memswap_limit='128m',
            cpu_period=100000,
            cpu_quota=50000,
            cap_drop=['ALL'],
            read_only=True
        )
        
        try:
            result = container.wait(timeout=2)
            logs = container.logs().decode('utf-8', errors='ignore')
            container.remove()
            
            if os.path.exists(temp_input_path): os.remove(temp_input_path)

            if result['StatusCode'] != 0:
                return False, f"執行錯誤 (RE) [Code: {result['StatusCode']}]: {logs}"
            return True, normalize_output(logs)
            
        except Exception:
            try: container.kill(); container.remove()
            except: pass
            if os.path.exists(temp_input_path): os.remove(temp_input_path)
            return False, "執行逾時 (TLE)"

    except Exception as e:
        if os.path.exists(temp_input_path): os.remove(temp_input_path)
        return False, f"系統錯誤: {str(e)}"

# --- 路由與視圖 ---

@app.route('/')
def home():
    db = get_db()
    problems = db.execute('SELECT id, title, description, image_filename FROM problems').fetchall()
    
    user_stats = None
    solved_problem_ids = []

    if 'user_id' in session:
        user_id = session['user_id']
        
        # 1. AC 題目 ID
        rows = db.execute("SELECT DISTINCT problem_id FROM submissions WHERE user_id = ? AND status = 'AC'", (user_id,)).fetchall()
        solved_problem_ids = [row['problem_id'] for row in rows]
        
        # 2. 正確率
        total_sub = db.execute("SELECT COUNT(*) FROM submissions WHERE user_id = ?", (user_id,)).fetchone()[0]
        ac_sub = db.execute("SELECT COUNT(*) FROM submissions WHERE user_id = ? AND status = 'AC'", (user_id,)).fetchone()[0]
        accuracy = round((ac_sub / total_sub * 100), 1) if total_sub > 0 else 0
        
        # 3. 排名
        ranking_query = '''
            SELECT user_id, COUNT(DISTINCT problem_id) as ac_count 
            FROM submissions 
            WHERE status = 'AC' 
            GROUP BY user_id 
            ORDER BY ac_count DESC
        '''
        rankings = db.execute(ranking_query).fetchall()
        
        my_rank = "N/A"
        for idx, r in enumerate(rankings):
            if r['user_id'] == user_id:
                my_rank = idx + 1
                break
        
        if my_rank == "N/A" and total_sub > 0:
            my_rank = len(rankings) + 1
        elif my_rank == "N/A":
            my_rank = "-"

        user_stats = {
            'username': session['username'],
            'solved_count': len(solved_problem_ids),
            'total_submissions': total_sub,
            'accuracy': accuracy,
            'rank': my_rank
        }

    return render_template('home.html', problems=problems, user_stats=user_stats, solved_ids=solved_problem_ids)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        
        if db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            return render_template('register.html', error="帳號已存在")
        
        hashed_pw = generate_password_hash(password)
        db.execute('INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)',
                   (username, hashed_pw, time.time()))
        db.commit()
        write_log(f"新用戶註冊: {username}")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['logged_in'] = True
            
            write_log(f"用戶登入: {username}")
            if user['role'] == 'admin':
                return redirect(url_for('admin'))
            
            return redirect(url_for('home'))
        else:
            return render_template('login.html', error="帳號或密碼錯誤")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/problem/<int:problem_id>', methods=['GET', 'POST'])
def problem_view(problem_id):
    db = get_db()
    current_problem = db.execute('SELECT * FROM problems WHERE id = ?', (problem_id,)).fetchone()
    if not current_problem: return render_template('404.html'), 404

    problems = db.execute('SELECT id, title FROM problems').fetchall()
    output = ""
    code_content = ""
    status = None
    
    try: problem_samples = json.loads(current_problem['samples']) 
    except: problem_samples = []

    # GET: 還原暫存
    if request.method == 'GET':
        if 'temp_code' in session and session.get('temp_problem_id') == problem_id:
            code_content = session['temp_code']
            flash("已為您還原未登入前的程式碼進度！", "info")
            session.pop('temp_code', None)
            session.pop('temp_problem_id', None)

    # POST: 提交
    if request.method == 'POST' and 'submit_code' in request.form:
        file = request.files.get('file')
        text_code = request.form.get('code')
        if file and file.filename != '': code_content = file.read().decode('utf-8', errors='ignore')
        elif text_code: code_content = text_code
        else: code_content = ""

        if 'user_id' not in session:
            session['temp_code'] = code_content
            session['temp_problem_id'] = problem_id
            flash("請先登入，系統已暫存您的程式碼，登入後將自動還原。", "warning")
            return redirect(url_for('login'))

        client_ip = get_real_ip()
        current_time = time.time()
        
        log_row = db.execute('SELECT last_submit_time FROM submission_logs WHERE ip = ?', (client_ip,)).fetchone()
        last_time = log_row['last_submit_time'] if log_row else 0
        if current_time - last_time < RATE_LIMIT_SECONDS:
            output = f"🚫 動作太快了！請等待 {int(RATE_LIMIT_SECONDS - (current_time - last_time))} 秒後再試。"
        elif not code_content:
            output = "錯誤：請提供程式碼"
        else:
            db.execute('INSERT OR REPLACE INTO submission_logs (ip, last_submit_time) VALUES (?, ?)', (client_ip, current_time))
            db.commit()

            unique_id = str(uuid.uuid4())
            src_file = os.path.join(TEMP_DIR, f"{unique_id}.cpp")
            exec_file = os.path.join(TEMP_DIR, f"{unique_id}.out")

            try:
                with open(src_file, 'w') as f: f.write(code_content)
                try: test_cases = json.loads(current_problem['test_cases']) 
                except: test_cases = []

                # 1. 編譯
                success, msg = compile_code(src_file, exec_file)
                
                if not success:
                    status = "CE"
                    output = f"編譯錯誤:\n{msg}"
                elif not test_cases:
                    status = "WA"; output = "錯誤：無測試資料"
                else:
                    # 2. 執行
                    all_passed = True
                    for i, case in enumerate(test_cases):
                        run_success, run_output = execute_code(exec_file, case['in'])
                        
                        if not run_success:
                            if "逾時" in run_output: status = "TLE"
                            elif "記憶體" in run_output: status = "MLE"
                            else: status = "RE"
                            output = run_output; all_passed = False; break
                        
                        if normalize_output(run_output) != normalize_output(case['out']):
                            status = "WA"
                            output = f"答案錯誤 (WA) - Case {i+1} 失敗。\n您的輸出:\n{normalize_output(run_output)}"
                            all_passed = False; break
                    
                    if all_passed:
                        status = "AC"
                        output = "恭喜！所有測試資料皆通過 (All Test Cases Passed)。"

                # 寫入資料庫
                if 'user_id' in session:
                    db.execute('INSERT INTO submissions (user_id, problem_id, status, code, timestamp) VALUES (?, ?, ?, ?, ?)',
                               (session['user_id'], problem_id, status, code_content, time.time()))
                    db.commit()
                write_log(f"提交結果 - {session['username']} - P{problem_id} - {status}")

            except Exception as e:
                output = f"系統錯誤: {str(e)}"
            finally:
                if os.path.exists(src_file): os.remove(src_file)
                if os.path.exists(exec_file): os.remove(exec_file)

    return render_template('index.html', problems=problems, current_problem=current_problem, 
                           problem_samples=problem_samples, output=output, code=code_content, status=status)

@app.route('/run_samples/<int:problem_id>', methods=['POST'])
def run_samples(problem_id):
    db = get_db()
    problem = db.execute('SELECT * FROM problems WHERE id = ?', (problem_id,)).fetchone()
    if not problem: return {"error": "題目不存在"}, 404
    
    try: samples = json.loads(problem['samples'])
    except: samples = []
    
    if not samples: return {"error": "本題沒有範例測資"}, 400

    user_code = request.json.get('code', '')
    if not user_code: return {"error": "請輸入程式碼"}, 400

    unique_id = str(uuid.uuid4())
    src_file = os.path.join(TEMP_DIR, f"{unique_id}.cpp")
    exec_file = os.path.join(TEMP_DIR, f"{unique_id}.out")
    
    try:
        with open(src_file, 'w') as f: f.write(user_code)
        
        success, msg = compile_code(src_file, exec_file)
        if not success:
            return {"status": "CE", "message": msg}

        results = []
        for idx, sample in enumerate(samples):
            s_in = sample['in']
            s_out = normalize_output(sample['out'])
            
            run_success, run_output = execute_code(exec_file, s_in)
            
            user_out = normalize_output(run_output) if run_success else run_output
            is_correct = (user_out == s_out)
            
            results.append({
                "id": idx + 1,
                "input": s_in,
                "expected": s_out,
                "actual": user_out,
                "pass": is_correct,
                "error": not run_success and ("錯誤" in user_out or "逾時" in user_out)
            })

        return {"status": "OK", "results": results}

    except Exception as e:
        return {"error": str(e)}, 500
    finally:
        if os.path.exists(src_file): os.remove(src_file)
        if os.path.exists(exec_file): os.remove(exec_file)


@app.route('/editor')
def editor():
    """單純 C++ 編輯器頁面：不綁題目、不寫入提交紀錄。"""
    return render_template('editor.html')

@app.route('/run_custom', methods=['POST'])
def run_custom():
    """執行編輯器中的 C++ 程式，使用使用者自訂 stdin。"""
    payload = request.get_json(silent=True) or {}
    user_code = payload.get('code', '')
    input_data = payload.get('input', '')

    if not user_code.strip():
        return {"error": "請先輸入 C++ 程式碼"}, 400

    # 簡單防刷，避免公開編輯器被連續大量執行。
    db = get_db()
    client_ip = get_real_ip()
    current_time = time.time()
    log_row = db.execute('SELECT last_submit_time FROM submission_logs WHERE ip = ?', (client_ip,)).fetchone()
    last_time = log_row['last_submit_time'] if log_row else 0
    if current_time - last_time < RATE_LIMIT_SECONDS:
        wait_seconds = int(RATE_LIMIT_SECONDS - (current_time - last_time))
        return {"error": f"動作太快了，請等待 {wait_seconds} 秒後再試。"}, 429

    db.execute('INSERT OR REPLACE INTO submission_logs (ip, last_submit_time) VALUES (?, ?)', (client_ip, current_time))
    db.commit()

    unique_id = str(uuid.uuid4())
    src_file = os.path.join(TEMP_DIR, f"editor_{unique_id}.cpp")
    exec_file = os.path.join(TEMP_DIR, f"editor_{unique_id}.out")

    try:
        with open(src_file, 'w', encoding='utf-8') as f:
            f.write(user_code)

        success, msg = compile_code(src_file, exec_file)
        if not success:
            write_log("編輯器執行結果 - CE")
            return {"status": "CE", "output": f"編譯錯誤:\n{msg}"}

        run_success, run_output = execute_code(exec_file, input_data)
        if not run_success:
            status = "TLE" if "逾時" in run_output else "RE"
            write_log(f"編輯器執行結果 - {status}")
            return {"status": status, "output": run_output}

        write_log("編輯器執行結果 - OK")
        return {"status": "OK", "output": run_output}

    except Exception as e:
        return {"error": f"系統錯誤: {str(e)}"}, 500
    finally:
        if os.path.exists(src_file): os.remove(src_file)
        if os.path.exists(exec_file): os.remove(exec_file)

@app.route('/get_hint/<int:problem_id>', methods=['POST'])
def get_hint(problem_id):
    if 'user_id' not in session:
        return {"error": "請先登入才能使用 AI 功能"}, 401

    db = get_db()
    client_ip = get_real_ip()
    current_time = time.time()
    
    log_row = db.execute('SELECT last_request_time FROM ai_logs WHERE ip = ?', (client_ip,)).fetchone()
    time_diff = current_time - (log_row['last_request_time'] if log_row else 0)
    
    if time_diff < AI_RATE_LIMIT_SECONDS:
        return {"error": f"AI 冷卻中，請等待 {int(AI_RATE_LIMIT_SECONDS - time_diff)} 秒"}, 429
    
    db.execute('INSERT OR REPLACE INTO ai_logs (ip, last_request_time) VALUES (?, ?)', (client_ip, current_time))
    db.commit()

    problem = db.execute('SELECT * FROM problems WHERE id = ?', (problem_id,)).fetchone()
    if not problem: return {"error": "題目不存在"}, 404

    user_code = request.json.get('code', '')

    prompt = f"""
    你是一位循循善誘的程式設計老師。學生遇到了一道題目，請提供「解題思路」與「邏輯提示」，但**絕對不要直接給出完整的程式碼答案**。
    
    【題目名稱】：{problem['title']}
    【題目敘述】：
    {problem['description']}
    
    【學生目前的程式碼】：
    {user_code if user_code else "(學生尚未開始寫)"}
    
    請用繁體中文回答，條列式說明解題步驟、可能需要的演算法或資料結構，以及需要注意的邊界條件。
    """

    try:
        response = requests.post(OLLAMA_API_URL, json={"model": AI_MODEL, "prompt": prompt, "stream": False}, timeout=60)
        if response.status_code == 200: return {"hint": response.json()['response']}
        return {"error": f"AI Error: {response.status_code}"}, 500
    except Exception as e: return {"error": str(e)}, 500

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('logged_in') or session.get('role') != 'admin': 
        return redirect(url_for('login'))
    
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
        write_log(f"管理員新增題目 - Title: {title}")
        return redirect(url_for('admin'))

    problems = db.execute('SELECT * FROM problems ORDER BY id DESC').fetchall()
    return render_template('admin.html', problems=problems)

@app.route('/admin/export')
def export_problems():
    if not session.get('logged_in') or session.get('role') != 'admin': 
        return redirect(url_for('login'))
    
    db = get_db()
    problems = db.execute('SELECT * FROM problems').fetchall()
    
    export_data = []
    for p in problems:
        p_dict = dict(p)
        try: p_dict['samples'] = json.loads(p['samples'])
        except: p_dict['samples'] = []
        try: p_dict['test_cases'] = json.loads(p['test_cases'])
        except: p_dict['test_cases'] = []
        export_data.append(p_dict)

    json_str = json.dumps(export_data, ensure_ascii=False, indent=4)
    response = make_response(json_str)
    response.headers['Content-Type'] = 'application/json'
    response.headers['Content-Disposition'] = 'attachment; filename=problems_backup.json'
    
    write_log("管理員匯出備份 (Export)")
    return response

@app.route('/admin/import', methods=['POST'])
def import_problems():
    if not session.get('logged_in') or session.get('role') != 'admin': 
        return redirect(url_for('login'))
    
    file = request.files.get('backup_file')
    if not file or file.filename == '': return "請選擇檔案", 400

    try:
        data = json.load(file)
        if not isinstance(data, list): return "格式錯誤", 400

        db = get_db()
        count = 0
        for p in data:
            samples_json = json.dumps(p.get('samples', []))
            test_cases_json = json.dumps(p.get('test_cases', []))
            title = p.get('title', '未命名')
            description = p.get('description', '')
            image_filename = p.get('image_filename', None)

            db.execute('''
                INSERT INTO problems (title, description, image_filename, samples, test_cases) 
                VALUES (?, ?, ?, ?, ?)
            ''', (title, description, image_filename, samples_json, test_cases_json))
            count += 1
            
        db.commit()
        write_log(f"管理員匯入備份 - 共 {count} 題")
        return redirect(url_for('admin'))
    except Exception as e:
        return f"匯入失敗: {str(e)}", 500

@app.route('/edit/<int:problem_id>', methods=['GET', 'POST'])
def edit_problem(problem_id):
    if not session.get('logged_in') or session.get('role') != 'admin': 
        return redirect(url_for('login'))
    
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
        write_log(f"管理員編輯題目 - ID: {problem_id}")
        return redirect(url_for('admin'))

    problem = db.execute('SELECT * FROM problems WHERE id = ?', (problem_id,)).fetchone()
    if not problem: return render_template('404.html'), 404

    try: samples = json.loads(problem['samples'])
    except: samples = []
    
    try: test_cases = json.loads(problem['test_cases'])
    except: test_cases = []

    return render_template('edit.html', problem=problem, samples=samples, test_cases=test_cases)

@app.route('/delete/<int:problem_id>')
def delete_problem(problem_id):
    if not session.get('logged_in') or session.get('role') != 'admin': 
        return redirect(url_for('login'))
    
    db = get_db()
    problem = db.execute('SELECT title, image_filename FROM problems WHERE id = ?', (problem_id,)).fetchone()
    if problem:
        if problem['image_filename']:
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], problem['image_filename'])
            if os.path.exists(img_path): os.remove(img_path)
        
        db.execute('DELETE FROM problems WHERE id = ?', (problem_id,))
        db.commit()
        write_log(f"管理員刪除題目 - ID: {problem_id}")
        
    return redirect(url_for('admin'))

@app.errorhandler(404)
def page_not_found(e): 
    return render_template('404.html'), 404

@app.route('/favicon.ico')
def favicon(): 
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico')

with app.app_context(): 
    init_db()

if __name__ == '__main__':
    # 關閉 Debug 模式以避免重載導致的額外連線問題
    app.run(debug=False, host='0.0.0.0', port=8080)