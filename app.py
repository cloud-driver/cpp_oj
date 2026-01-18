import os
import uuid
import sqlite3
import json
import time
import docker
from docker.errors import ContainerError
from flask import Flask, render_template, request, redirect, url_for, session, g, send_from_directory

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# --- 設定與路徑 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'cpp_oj.db')
TEMP_DIR = os.path.join(BASE_DIR, 'temp_code')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/uploads')
LOG_FILE = os.path.join(BASE_DIR, 'oj_events.log')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ADMIN_PASSWORD = 'your_password'
RATE_LIMIT_SECONDS = 15
DOCKER_IMAGE = 'gcc:latest'

# Docker 設定
try:
    docker_client = docker.from_env()
except Exception as e:
    print("錯誤：無法連線到 Docker。")
    docker_client = None

if not os.path.exists(TEMP_DIR): os.makedirs(TEMP_DIR)
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)

def get_real_ip():
    if request.headers.getlist("CF-Connecting-IP"):
        return request.headers.get("CF-Connecting-IP")
    return request.remote_addr

def write_log(event_message):
    """
    格式：<ip> : <時間> : <事件>
    """
    ip = get_real_ip()
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    log_content = f"{ip} : {current_time} : {event_message}"
    print(log_content)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_content + '\n')
    except Exception as e:
        print(f"寫入 Log 失敗: {e}")

# --- 資料庫邏輯 ---
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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS submission_logs (
                ip TEXT PRIMARY KEY,
                last_submit_time REAL
            )
        ''')
        db.commit()

def normalize_output(text):
    if not text: return ""
    return text.strip().replace('\r\n', '\n')

# --- Docker 沙箱執行函式 ---
def run_in_sandbox(source_filename, input_filename):
    if not docker_client: return False, "系統錯誤：Docker 未啟動"
    
    src_name = os.path.basename(source_filename)
    in_name = os.path.basename(input_filename)
    exec_name = src_name.replace('.cpp', '.out')
    volumes = {TEMP_DIR: {'bind': '/app', 'mode': 'rw'}}

    try:
        # 編譯
        docker_client.containers.run(
            image=DOCKER_IMAGE,
            command=f"g++ {src_name} -o {exec_name}",
            volumes=volumes,
            working_dir='/app',
            remove=True,
            network_disabled=True,
            mem_limit='256m'
        )
    except ContainerError as e:
        return False, f"編譯錯誤:\n{e.stderr.decode('utf-8', errors='ignore')}"
    except Exception as e:
        return False, f"編譯系統錯誤: {str(e)}"

    # 執行
    try:
        container = docker_client.containers.run(
            image=DOCKER_IMAGE,
            command=f"sh -c './{exec_name} < {in_name}'",
            volumes=volumes,
            working_dir='/app',
            detach=True,
            network_disabled=True,
            mem_limit='128m',
            pids_limit=20,
            cpu_period=100000,
            cpu_quota=50000
        )
        try:
            result = container.wait(timeout=2)
            logs = container.logs().decode('utf-8', errors='ignore')
            container.remove()
            if result['StatusCode'] != 0: return False, f"執行錯誤 (RE):\n{logs}"
            return True, logs
        except Exception:
            container.kill()
            container.remove()
            return False, "執行逾時 (TLE)"
    except Exception as e:
        return False, f"執行系統錯誤: {str(e)}"

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
        return render_template('404.html'), 404

    problems = db.execute('SELECT id, title FROM problems').fetchall()
    output = ""
    code_content = ""
    status = None
    problem_samples = []

    try: problem_samples = json.loads(current_problem['samples'])
    except: problem_samples = []

    if request.method == 'POST' and 'submit_code' in request.form:
        client_ip = get_real_ip()
        current_time = time.time()
        
        log_row = db.execute('SELECT last_submit_time FROM submission_logs WHERE ip = ?', (client_ip,)).fetchone()
        last_submit_time = log_row['last_submit_time'] if log_row else 0
        time_diff = current_time - last_submit_time
        
        file = request.files.get('file')
        text_code = request.form.get('code')
        if file and file.filename != '':
            code_content = file.read().decode('utf-8', errors='ignore')
        elif text_code:
            code_content = text_code

        if time_diff < RATE_LIMIT_SECONDS:
            wait_time = int(RATE_LIMIT_SECONDS - time_diff)
            output = f"🚫 動作太快了！請等待 {wait_time} 秒後再試。"
            write_log(f"提交被攔截 (Rate Limit) - Problem {problem_id} - Wait {wait_time}s")
        else:
            db.execute('INSERT OR REPLACE INTO submission_logs (ip, last_submit_time) VALUES (?, ?)', (client_ip, current_time))
            db.commit()
            
            if not code_content:
                output = "錯誤：請提供程式碼"
            else:
                unique_id = str(uuid.uuid4())
                source_filename = os.path.join(TEMP_DIR, f"{unique_id}.cpp")
                input_filename = os.path.join(TEMP_DIR, f"{unique_id}.in")
                exec_filename = os.path.join(TEMP_DIR, f"{unique_id}.out")

                try:
                    with open(source_filename, 'w') as f: f.write(code_content)
                    
                    try: test_cases = json.loads(current_problem['test_cases'])
                    except: test_cases = []
                    
                    all_passed = True
                    if not test_cases:
                        status = "WA"
                        output = "錯誤：本題尚未設定測試資料。"
                        all_passed = False

                    for i, case in enumerate(test_cases):
                        with open(input_filename, 'w') as f: f.write(case['in'])
                        
                        success, run_output = run_in_sandbox(source_filename, input_filename)
                        
                        if not success:
                            if "編譯錯誤" in run_output: status = "CE"
                            elif "逾時" in run_output: status = "TLE"
                            else: status = "RE"
                            output = run_output
                            all_passed = False
                            break
                        
                        if normalize_output(run_output) != normalize_output(case['out']):
                            status = "WA"
                            output = f"答案錯誤 (WA) - Case {i+1} 失敗。\n您的輸出:\n{normalize_output(run_output)}"
                            all_passed = False
                            break
                    
                    if all_passed:
                        status = "AC"
                        output = "恭喜！所有測試資料皆通過 (All Test Cases Passed)。"

                    write_log(f"提交結果 - Problem {problem_id} - Status: {status}")

                except Exception as e:
                    output = f"系統錯誤: {str(e)}"
                    write_log(f"系統錯誤 - Problem {problem_id} - {str(e)}")
                finally:
                    for f in [source_filename, input_filename, exec_filename]:
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
        write_log(f"管理員編輯題目 - ID: {problem_id} - Title: {title}")
        return redirect(url_for('admin'))
    
    problem = db.execute('SELECT * FROM problems WHERE id = ?', (problem_id,)).fetchone()
    if not problem:
        return render_template('404.html'), 404
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
            write_log("管理員登入成功")
            return redirect(url_for('admin'))
        else:
            error = '密碼錯誤'
            write_log("管理員登入失敗 (密碼錯誤)")
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    write_log("管理員登出")
    return redirect(url_for('home'))

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
        write_log(f"管理員新增題目 - Title: {title}")
        return redirect(url_for('admin'))

    problems = db.execute('SELECT * FROM problems ORDER BY id DESC').fetchall()
    return render_template('admin.html', problems=problems)

@app.route('/delete/<int:problem_id>')
def delete_problem(problem_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    db = get_db()
    problem = db.execute('SELECT title, image_filename FROM problems WHERE id = ?', (problem_id,)).fetchone()
    if problem:
        if problem['image_filename']:
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], problem['image_filename'])
            if os.path.exists(img_path): os.remove(img_path)
        
        db.execute('DELETE FROM problems WHERE id = ?', (problem_id,))
        db.commit()
        write_log(f"管理員刪除題目 - ID: {problem_id} - Title: {problem['title']}")
        
    return redirect(url_for('admin'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)