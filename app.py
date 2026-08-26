import sqlite3
import math
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super_secret_key_attendance'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

def get_db_connection():
    conn = sqlite3.connect('attendance.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            department TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            course_code TEXT NOT NULL,
            course_name TEXT NOT NULL,
            units INTEGER DEFAULT 3,
            attended_classes INTEGER DEFAULT 0,
            total_classes INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

class User(UserMixin):
    def __init__(self, id, username, email, department):
        self.id = id
        self.username = username
        self.email = email
        self.department = department

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user:
        return User(id=user['id'], username=user['username'], email=user['email'], department=user['department'])
    return None

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        department = request.form.get('department')
        password = request.form.get('password')

        if not username or not email or not password:
            flash('Please fill in all fields.')
            return render_template('register.html')
        
        hashed_pw = generate_password_hash(password)
        
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, email, password, department) VALUES (?, ?, ?, ?)',
                         (username, email, hashed_pw, department))
            conn.commit()
            flash('Account created successfully! Please log in.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email or Username already registered.')
        finally:
            conn.close()
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            user_obj = User(id=user['id'], username=user['username'], email=user['email'], department=user['department'])
            login_user(user_obj)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.')
            
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    courses_raw = conn.execute('SELECT * FROM courses WHERE user_id = ?', (current_user.id,)).fetchall()
    conn.close()

    courses = []
    total_attended = 0
    total_held = 0
    total_units = 0
    TARGET_PCT = 70.0  # 70% Attendance Target

    for c in courses_raw:
        attended = c['attended_classes']
        total = c['total_classes']
        pct = round((attended / total) * 100, 1) if total > 0 else 100.0

        # Calculate needed consecutive classes to reach 70%
        needed_classes = 0
        if total > 0 and pct < TARGET_PCT:
            needed_classes = math.ceil((0.7 * total - attended) / 0.3)
            needed_classes = max(needed_classes, 0)

        courses.append({
            'id': c['id'],
            'course_code': c['course_code'],
            'course_name': c['course_name'],
            'units': c['units'],
            'attended_classes': attended,
            'total_classes': total,
            'percentage': pct if total > 0 else 0.0,
            'status': 'Safe' if pct >= TARGET_PCT else 'At Risk',
            'needed_classes': needed_classes
        })

        total_attended += attended
        total_held += total
        total_units += c['units']

    overall_percentage = round((total_attended / total_held) * 100, 1) if total_held > 0 else 0.0

    return render_template(
        'profile.html',
        courses=courses,
        total_attended=total_attended,
        total_held=total_held,
        total_units=total_units,
        overall_percentage=overall_percentage,
        overall_status='Safe' if overall_percentage >= TARGET_PCT or total_held == 0 else 'At Risk'
    )

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    department = request.form.get('department')
    if department:
        conn = get_db_connection()
        conn.execute('UPDATE users SET department = ? WHERE id = ?', (department, current_user.id))
        conn.commit()
        conn.close()
        flash('Department updated successfully!')
    return redirect(url_for('dashboard'))

@app.route('/add_course', methods=['POST'])
@login_required
def add_course():
    code = request.form.get('course_code')
    name = request.form.get('course_name')
    units = int(request.form.get('units', 3))

    conn = get_db_connection()
    conn.execute('''
        INSERT INTO courses (user_id, course_code, course_name, units, attended_classes, total_classes)
        VALUES (?, ?, ?, ?, 0, 0)
    ''', (current_user.id, code, name, units))
    conn.commit()
    conn.close()

    flash(f'Course {code} added successfully!')
    return redirect(url_for('dashboard'))

@app.route('/log_attendance/<int:course_id>/<string:status>', methods=['POST'])
@login_required
def log_attendance(course_id, status):
    conn = get_db_connection()
    course = conn.execute('SELECT * FROM courses WHERE id = ? AND user_id = ?', (course_id, current_user.id)).fetchone()
    
    if course:
        new_total = course['total_classes'] + 1
        new_attended = course['attended_classes'] + 1 if status == 'present' else course['attended_classes']
        
        conn.execute('''
            UPDATE courses 
            SET attended_classes = ?, total_classes = ? 
            WHERE id = ? AND user_id = ?
        ''', (new_attended, new_total, course_id, current_user.id))
        conn.commit()
    
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/delete_course/<int:course_id>', methods=['POST'])
@login_required
def delete_course(course_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM courses WHERE id = ? AND user_id = ?', (course_id, current_user.id))
    conn.commit()
    conn.close()
    flash('Course deleted successfully!')
    return redirect(url_for('dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)