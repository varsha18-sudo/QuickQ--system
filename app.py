"""
QuickQ College Queue Token Management System
Single file Streamlit application - With Aggressive Dropdown Visibility Fix
Run with: streamlit run app.py
"""

import streamlit as st
from datetime import datetime
import sqlite3
import pandas as pd
import hashlib

# ------------------------------------------------------------------------------
# Database Setup
# ------------------------------------------------------------------------------
def init_database():
    """Initialize SQLite database and create all tables"""
    conn = sqlite3.connect('quickq_database.db')
    c = conn.cursor()
    
    # Students table with authentication
    c.execute('''CREATE TABLE IF NOT EXISTS students
                 (roll_number TEXT PRIMARY KEY,
                  name TEXT,
                  password TEXT,
                  is_defaulter INTEGER DEFAULT 0,
                  created_at TEXT)''')
    
    # Defaulters table (for easy lookup)
    c.execute('''CREATE TABLE IF NOT EXISTS defaulters
                 (roll_number TEXT PRIMARY KEY,
                  name TEXT,
                  added_date TEXT,
                  added_by TEXT,
                  reason TEXT,
                  FOREIGN KEY (roll_number) REFERENCES students(roll_number))''')
    
    # Tokens table
    c.execute('''CREATE TABLE IF NOT EXISTS tokens
                 (token_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  token_number INTEGER,
                  student_roll TEXT,
                  student_name TEXT,
                  department TEXT,
                  subject TEXT,
                  slot TEXT,
                  issued_time TEXT,
                  status TEXT DEFAULT 'pending',
                  FOREIGN KEY (student_roll) REFERENCES students(roll_number))''')
    
    # Queue state table
    c.execute('''CREATE TABLE IF NOT EXISTS queue_state
                 (department TEXT PRIMARY KEY,
                  current_token INTEGER,
                  last_token INTEGER,
                  paused INTEGER DEFAULT 0,
                  avg_wait_min INTEGER DEFAULT 2,
                  total_issued INTEGER DEFAULT 0)''')
    
    # Login history table
    c.execute('''CREATE TABLE IF NOT EXISTS login_history
                 (login_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  student_roll TEXT,
                  student_name TEXT,
                  login_time TEXT,
                  status TEXT,
                  FOREIGN KEY (student_roll) REFERENCES students(roll_number))''')
    
    # Defaulter log table
    c.execute('''CREATE TABLE IF NOT EXISTS defaulter_log
                 (log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  roll_number TEXT,
                  name TEXT,
                  action TEXT,
                  action_date TEXT,
                  performed_by TEXT)''')
    
    # Admin table (keeping for compatibility but not using for auth)
    c.execute('''CREATE TABLE IF NOT EXISTS admins
                 (admin_id TEXT PRIMARY KEY,
                  password TEXT,
                  name TEXT,
                  department TEXT)''')
    
    # Initialize queue state for departments if not exists
    departments = ['Submission', 'Student Section', 'Accounts Section', 'Canteen', 'Bus Line']
    for dept in departments:
        c.execute("INSERT OR IGNORE INTO queue_state (department, current_token, last_token, total_issued) VALUES (?, 1, 0, 0)", (dept,))
    
    conn.commit()
    conn.close()

# Call database initialization
init_database()

# ------------------------------------------------------------------------------
# Database helper functions
# ------------------------------------------------------------------------------
def get_db_connection():
    """Get database connection"""
    return sqlite3.connect('quickq_database.db')

def hash_password(password):
    """Hash password for security"""
    return hashlib.sha256(password.encode()).hexdigest()

# Student Authentication Functions
def register_student(roll_number, name, password):
    """Register a new student"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO students (roll_number, name, password, created_at)
                     VALUES (?, ?, ?, ?)''',
                  (roll_number, name, hash_password(password), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def verify_student_login(roll_number, password):
    """Verify student login credentials"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT roll_number, name, password, is_defaulter FROM students WHERE roll_number = ?", (roll_number,))
    student = c.fetchone()
    conn.close()
    
    if student:
        stored_password = student[2]
        if stored_password == hash_password(password):
            return {
                'roll_number': student[0],
                'name': student[1],
                'is_defaulter': student[3]
            }
    return None

def check_is_defaulter(roll_number):
    """Check if student is defaulter"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT is_defaulter FROM students WHERE roll_number = ?", (roll_number,))
    result = c.fetchone()
    conn.close()
    return result and result[0] == 1

def log_login_attempt(roll_number, name, status):
    """Log login attempts"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO login_history (student_roll, student_name, login_time, status)
                 VALUES (?, ?, ?, ?)''',
              (roll_number, name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status))
    conn.commit()
    conn.close()

def parse_multiple_names(input_text):
    """Parse comma-separated or newline-separated names"""
    if not input_text:
        return []
    
    text = input_text.replace(',', '\n')
    names = [name.strip() for name in text.split('\n') if name.strip()]
    return names

def add_multiple_to_defaulters(names_input, reason, performed_by="admin"):
    """Add multiple students to defaulter list"""
    names = parse_multiple_names(names_input)
    if not names:
        return False, "No valid names provided"
    
    success_count = 0
    
    for name in names:
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT roll_number FROM students WHERE name LIKE ?", (f'%{name}%',))
        students = c.fetchall()
        
        if students:
            for student in students:
                roll_number = student[0]
                c.execute("UPDATE students SET is_defaulter = 1 WHERE roll_number = ?", (roll_number,))
                c.execute('''INSERT OR REPLACE INTO defaulters (roll_number, name, added_date, added_by, reason)
                             VALUES (?, ?, ?, ?, ?)''',
                          (roll_number, name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), performed_by, reason))
                c.execute('''INSERT INTO defaulter_log (roll_number, name, action, action_date, performed_by)
                             VALUES (?, ?, ?, ?, ?)''',
                          (roll_number, name, 'added', datetime.now().strftime("%Y-%m-%d %H:%M:%S"), performed_by))
                success_count += 1
        else:
            fake_roll = f"TEMP_{datetime.now().strftime('%Y%m%d%H%M%S')}_{success_count}"
            c.execute('''INSERT INTO students (roll_number, name, password, is_defaulter, created_at)
                         VALUES (?, ?, ?, 1, ?)''',
                      (fake_roll, name, hash_password("temp123"), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            c.execute('''INSERT INTO defaulters (roll_number, name, added_date, added_by, reason)
                         VALUES (?, ?, ?, ?, ?)''',
                      (fake_roll, name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), performed_by, reason))
            success_count += 1
        
        conn.commit()
        conn.close()
    
    return True, f"Added {success_count} students to defaulters list"

def add_to_defaulters(roll_number, reason, performed_by="admin"):
    """Original function - kept for backward compatibility"""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT name FROM students WHERE roll_number = ?", (roll_number,))
    student = c.fetchone()
    
    if student:
        student_name = student[0]
        c.execute("UPDATE students SET is_defaulter = 1 WHERE roll_number = ?", (roll_number,))
        c.execute('''INSERT OR REPLACE INTO defaulters (roll_number, name, added_date, added_by, reason)
                     VALUES (?, ?, ?, ?, ?)''',
                  (roll_number, student_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), performed_by, reason))
        c.execute('''INSERT INTO defaulter_log (roll_number, name, action, action_date, performed_by)
                     VALUES (?, ?, ?, ?, ?)''',
                  (roll_number, student_name, 'added', datetime.now().strftime("%Y-%m-%d %H:%M:%S"), performed_by))
        conn.commit()
        success = True
    else:
        success = False
    
    conn.close()
    return success

def remove_from_defaulters(roll_number, performed_by="admin"):
    """Remove student from defaulter list"""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT name FROM students WHERE roll_number = ?", (roll_number,))
    student = c.fetchone()
    
    if student:
        student_name = student[0]
        c.execute("UPDATE students SET is_defaulter = 0 WHERE roll_number = ?", (roll_number,))
        c.execute("DELETE FROM defaulters WHERE roll_number = ?", (roll_number,))
        c.execute('''INSERT INTO defaulter_log (roll_number, name, action, action_date, performed_by)
                     VALUES (?, ?, ?, ?, ?)''',
                  (roll_number, student_name, 'removed', datetime.now().strftime("%Y-%m-%d %H:%M:%S"), performed_by))
        conn.commit()
        success = True
    else:
        success = False
    
    conn.close()
    return success

def get_all_defaulters():
    """Get list of all defaulters"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''SELECT d.roll_number, d.name, d.added_date, d.reason 
                 FROM defaulters d
                 ORDER BY d.added_date DESC''')
    defaulters = c.fetchall()
    conn.close()
    return defaulters

def get_all_students():
    """Get all students"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT roll_number, name, is_defaulter, created_at FROM students ORDER BY created_at DESC")
    students = c.fetchall()
    conn.close()
    return students

def search_student(query):
    """Search for a student by roll number or name"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''SELECT roll_number, name, is_defaulter 
                 FROM students 
                 WHERE roll_number LIKE ? OR name LIKE ?
                 LIMIT 10''', (f'%{query}%', f'%{query}%'))
    results = c.fetchall()
    conn.close()
    return results

# Token Management Functions
def save_token(student_roll, student_name, token_number, department, subject, slot):
    """Save token to database"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO tokens 
                 (token_number, student_roll, student_name, department, subject, slot, issued_time, status)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (token_number, student_roll, student_name, department, subject, slot, 
               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'pending'))
    conn.commit()
    conn.close()

def get_next_token_number(department):
    """Generate next token number from database"""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT last_token, total_issued FROM queue_state WHERE department = ?", (department,))
    result = c.fetchone()
    
    if result:
        if result[1] >= 80:
            conn.close()
            return None
        
        new_token = result[0] + 1
        new_total = result[1] + 1
        c.execute("UPDATE queue_state SET last_token = ?, total_issued = ? WHERE department = ?",
                  (new_token, new_total, department))
    else:
        new_token = 1
        new_total = 1
        c.execute("INSERT INTO queue_state (department, current_token, last_token, total_issued) VALUES (?, 1, ?, ?)",
                  (department, new_token, new_total))
    
    conn.commit()
    conn.close()
    return new_token

def get_queue_state(department):
    """Get queue state from database"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM queue_state WHERE department = ?", (department,))
    result = c.fetchone()
    conn.close()
    
    if result:
        return {
            'current': result[1],
            'last': result[2],
            'paused': bool(result[3]),
            'avg_wait_min': result[4],
            'total_issued': result[5]
        }
    return {
        'current': 1,
        'last': 0,
        'paused': False,
        'avg_wait_min': 2,
        'total_issued': 0
    }

def update_current_token(department):
    """Move to next token"""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT current_token, last_token FROM queue_state WHERE department = ?", (department,))
    result = c.fetchone()
    
    if result and result[0] < result[1]:
        new_current = result[0] + 1
        c.execute("UPDATE queue_state SET current_token = ? WHERE department = ?", (new_current, department))
        c.execute('''UPDATE tokens SET status = 'completed' 
                     WHERE department = ? AND token_number = ?''', (department, result[0]))
        conn.commit()
        conn.close()
        return True
    
    conn.close()
    return False

def toggle_queue_pause(department, paused):
    """Pause or resume queue"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE queue_state SET paused = ? WHERE department = ?", (1 if paused else 0, department))
    conn.commit()
    conn.close()

def get_student_current_token(student_roll, department):
    """Get student's current pending token"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''SELECT token_number, subject, slot FROM tokens 
                 WHERE student_roll = ? AND department = ? AND status = 'pending'
                 ORDER BY issued_time DESC LIMIT 1''', (student_roll, department))
    token = c.fetchone()
    conn.close()
    return token

def get_tokens_history(department=None, subject=None, student_roll=None):
    """Get token history with filters"""
    conn = get_db_connection()
    query = "SELECT * FROM tokens"
    params = []
    conditions = []
    
    if department:
        conditions.append("department = ?")
        params.append(department)
    if subject:
        conditions.append("subject = ?")
        params.append(subject)
    if student_roll:
        conditions.append("student_roll = ?")
        params.append(student_roll)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY issued_time DESC"
    
    c = conn.cursor()
    c.execute(query, params)
    tokens = c.fetchall()
    conn.close()
    return tokens

def get_login_history(limit=50):
    """Get recent login history"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''SELECT * FROM login_history 
                 ORDER BY login_time DESC LIMIT ?''', (limit,))
    history = c.fetchall()
    conn.close()
    return history

def verify_admin(password):
    """Verify admin password (case-insensitive)"""
    return password.lower() == "faculty"

# ------------------------------------------------------------------------------
# Page configuration
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="QuickQ · College Token System",
    page_icon="🎟️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ------------------------------------------------------------------------------
# Initialize session state
# ------------------------------------------------------------------------------
def initialize_session_state():
    """Initialize all session state variables"""
    
    if 'departments' not in st.session_state:
        st.session_state.departments = ['Submission', 'Student Section', 'Accounts Section', 'Canteen', 'Bus Line']
    
    if 'submission_subjects' not in st.session_state:
        st.session_state.submission_subjects = ['DBMS', 'OS', 'CT', 'IOT', 'DT', 'OE']
    
    if 'time_slots' not in st.session_state:
        st.session_state.time_slots = {
            'Slot 1': '8:30 AM - 10:30 AM',
            'Slot 2': '11:00 AM - 1:00 PM',
            'Slot 3': '2:00 PM - 4:30 PM'
        }
    
    if 'page' not in st.session_state:
        st.session_state.page = 'home'
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'user_type' not in st.session_state:
        st.session_state.user_type = None
    if 'user_data' not in st.session_state:
        st.session_state.user_data = None
    if 'selected_dept' not in st.session_state:
        st.session_state.selected_dept = None
    if 'selected_subject' not in st.session_state:
        st.session_state.selected_subject = None
    if 'admin_selected_subject' not in st.session_state:
        st.session_state.admin_selected_subject = None
    if 'admin_view' not in st.session_state:
        st.session_state.admin_view = 'dashboard'
    if 'admin_selected_section' not in st.session_state:
        st.session_state.admin_selected_section = 'Submission'

# Call initialization
initialize_session_state()

# ------------------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------------------
def people_ahead(dept, token):
    """Calculate number of people ahead"""
    state = get_queue_state(dept)
    if not state or token is None:
        return 0
    if token <= state['current']:
        return 0
    return token - state['current']

def waiting_time(dept, token):
    """Estimate waiting time"""
    ahead = people_ahead(dept, token)
    state = get_queue_state(dept)
    avg = state.get('avg_wait_min', 2) if state else 2
    return ahead * avg

def logout():
    """Handle logout"""
    st.session_state.logged_in = False
    st.session_state.user_type = None
    st.session_state.user_data = None
    st.session_state.page = 'home'
    st.session_state.admin_selected_subject = None
    st.session_state.admin_view = 'dashboard'
    st.session_state.admin_selected_section = 'Submission'
    st.rerun()

# ------------------------------------------------------------------------------
# CSS FIX FOR LOGIN BUTTONS AND DROPDOWNS
# ------------------------------------------------------------------------------
st.markdown("""
<style>
/* LOGIN BUTTON FIX - White background, black text, black border */
.login-btn button {
    background-color: white !important;
    color: black !important;
    border: 1px solid black !important;
}

.login-btn button:hover {
    background-color: #f0f0f0 !important;
    color: black !important;
}

/* Force all buttons to be visible */
.stButton > button {
    background-color: #FFFFFF !important;
    color: #000000 !important;
    border: 2px solid #000000 !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1) !important;
}

.stButton > button:hover {
    background-color: #f0f0f0 !important;
    border: 2px solid #000000 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1) !important;
}

/* Form submit buttons */
.stForm button[type="submit"] {
    background-color: #FFFFFF !important;
    color: #000000 !important;
    border: 2px solid #000000 !important;
}

/* Force entire app to white background */
.stApp, .stApp > div, section.main, .main, .block-container, html, body {
    background-color: #FFFFFF !important;
    background-image: none !important;
}

/* Force all text to black */
* {
    color: #000000 !important;
}

/* Override any dark theme colors */
:root {
    --primary-color: #2563eb !important;
    --background-color: #FFFFFF !important;
    --secondary-background-color: #F0F2F6 !important;
    --text-color: #000000 !important;
}

/* ============================================ */
/* DROPDOWN FIXES - WHITE BACKGROUND, BLACK TEXT */
/* ============================================ */

/* Main select container */
.stSelectbox div[data-baseweb="select"] {
    background-color: #FFFFFF !important;
    border: 2px solid #000000 !important;
    border-radius: 8px !important;
}

.stSelectbox div[data-baseweb="select"] > div {
    background-color: #FFFFFF !important;
    color: #000000 !important;
}

.stSelectbox div[data-baseweb="select"] span {
    color: #000000 !important;
}

.stSelectbox svg {
    fill: #000000 !important;
}

/* Dropdown popup container */
div[data-baseweb="popover"] {
    background-color: #FFFFFF !important;
    border: 2px solid #000000 !important;
    border-radius: 8px !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
}

div[data-baseweb="popover"] * {
    background-color: #FFFFFF !important;
    color: #000000 !important;
}

/* Menu inside popover */
div[data-baseweb="menu"] {
    background-color: #FFFFFF !important;
    border: none !important;
}

div[data-baseweb="menu"] * {
    background-color: #FFFFFF !important;
    color: #000000 !important;
}

/* Listbox container */
div[role="listbox"] {
    background-color: #FFFFFF !important;
}

div[role="listbox"] * {
    background-color: #FFFFFF !important;
    color: #000000 !important;
}

/* Individual option items */
div[role="option"] {
    background-color: #FFFFFF !important;
    color: #000000 !important;
    padding: 10px 16px !important;
    font-size: 14px !important;
    font-weight: 500 !important;
}

/* Hover state */
div[role="option"]:hover {
    background-color: #f0f0f0 !important;
    color: #000000 !important;
}

/* Selected/highlighted state */
div[role="option"][aria-selected="true"] {
    background-color: #e6e6e6 !important;
    color: #000000 !important;
    font-weight: 600 !important;
}

/* Focus state */
div[role="option"]:focus {
    background-color: #e6e6e6 !important;
    color: #000000 !important;
    outline: none !important;
}

/* Any list items inside dropdown */
ul[data-baseweb="menu"] li {
    background-color: #FFFFFF !important;
    color: #000000 !important;
}

ul[data-baseweb="menu"] li:hover {
    background-color: #f0f0f0 !important;
    color: #000000 !important;
}

/* ============================================ */
/* INPUT FIELDS */
/* ============================================ */
.stTextInput > div > div > input {
    background-color: #FFFFFF !important;
    color: #000000 !important;
    border: 2px solid #000000 !important;
    border-radius: 8px !important;
}

.stTextInput > div > div > input::placeholder {
    color: #6b7280 !important;
}

.stTextArea > div > div > textarea {
    background-color: #FFFFFF !important;
    color: #000000 !important;
    border: 2px solid #000000 !important;
    border-radius: 8px !important;
}

/* ============================================ */
/* METRICS */
/* ============================================ */
.stMetric {
    background-color: #FFFFFF !important;
    border: 2px solid #000000 !important;
    border-radius: 8px !important;
    padding: 12px !important;
}

/* ============================================ */
/* TABS */
/* ============================================ */
.stTabs [data-baseweb="tab"] {
    background-color: #FFFFFF !important;
    color: #000000 !important;
    border: 2px solid #000000 !important;
    border-radius: 8px !important;
    padding: 8px 16px !important;
    font-weight: 600 !important;
}

.stTabs [aria-selected="true"] {
    background-color: #2563eb !important;
    color: #FFFFFF !important;
}

/* ============================================ */
/* EXPANDER */
/* ============================================ */
.streamlit-expanderHeader {
    background-color: #FFFFFF !important;
    color: #000000 !important;
    border: 2px solid #000000 !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}

.streamlit-expanderContent {
    background-color: #FFFFFF !important;
    border: 2px solid #000000 !important;
    border-top: none !important;
    border-radius: 0 0 8px 8px !important;
    padding: 16px !important;
}

/* ============================================ */
/* ALERTS */
/* ============================================ */
.stAlert {
    background-color: #FFFFFF !important;
    border: 2px solid #000000 !important;
    border-radius: 8px !important;
}

/* ============================================ */
/* CUSTOM COMPONENTS */
/* ============================================ */
.custom-card {
    background: #FFFFFF !important;
    border: 2px solid #000000 !important;
    border-radius: 16px !important;
    padding: 2rem !important;
    text-align: center !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important;
}

.portal-icon {
    background: #2563eb !important;
    width: 80px !important;
    height: 80px !important;
    border-radius: 40px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    margin: 0 auto 1.5rem !important;
    font-size: 2.2rem !important;
    color: #FFFFFF !important;
    border: 2px solid #000000 !important;
}

.info-box {
    background: #eef2ff !important;
    border: 2px solid #000000 !important;
    border-radius: 12px !important;
    padding: 1rem !important;
    margin: 1rem 0 !important;
}

.slot-card {
    background: #1e293b !important;
    border: 2px solid #2563eb !important;
    border-radius: 12px !important;
    padding: 1rem !important;
    text-align: center !important;
    font-weight: 700 !important;
    color: #FFFFFF !important;
    margin: 0.5rem 0 !important;
}

.slot-card * {
    color: #FFFFFF !important;
}

.slot-time {
    color: #FFFFFF !important;
    font-size: 0.9rem !important;
    margin-top: 0.3rem !important;
}

.token-counter {
    background: #1e293b !important;
    color: #FFFFFF !important;
    padding: 0.5rem 1rem !important;
    border-radius: 2rem !important;
    display: inline-block !important;
    margin-bottom: 1rem !important;
    font-weight: 700 !important;
    border: 1px solid #FFFFFF !important;
}

.token-badge {
    background: #2563eb !important;
    color: #FFFFFF !important;
    font-size: 2.5rem !important;
    font-weight: 700 !important;
    padding: 0.5rem 2rem !important;
    border-radius: 4rem !important;
    display: inline-block !important;
    margin: 0.5rem 0 !important;
    border: 2px solid #000000 !important;
}

.capacity-full {
    background: #fee2e2 !important;
    border: 2px solid #dc2626 !important;
    color: #dc2626 !important;
    padding: 2rem !important;
    border-radius: 16px !important;
    text-align: center !important;
    font-weight: 700 !important;
    font-size: 1.25rem !important;
    margin: 2rem 0 !important;
}

.defaulter-card {
    background: #fee2e2 !important;
    border: 2px solid #dc2626 !important;
    border-radius: 16px !important;
    padding: 2rem !important;
    text-align: center !important;
    margin: 2rem 0 !important;
}

.defaulter-card h2, .defaulter-card p {
    color: #dc2626 !important;
    font-weight: 700 !important;
}

.stat-label {
    color: #000000 !important;
    font-size: 0.85rem !important;
    text-transform: uppercase !important;
    font-weight: 700 !important;
}

/* Remove any blur or transparency */
* {
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
    opacity: 1 !important;
}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# Header
# ------------------------------------------------------------------------------
col1, col2, col3 = st.columns([1, 2, 1])
with col1:
    if st.button("🏠 Home", use_container_width=True):
        if st.session_state.logged_in:
            logout()
        else:
            st.session_state.page = 'home'
            st.rerun()
with col2:
    st.markdown("<h2 style='text-align: center;'>🎟️ QuickQ · College</h2>", unsafe_allow_html=True)
with col3:
    if st.session_state.logged_in:
        user_info = st.session_state.user_data
        if user_info:
            if st.session_state.user_type == 'student':
                st.markdown(f"<p style='text-align: right;'>{user_info['name']}<br><small>{user_info['roll_number']}</small></p>", unsafe_allow_html=True)
            else:
                st.markdown(f"<p style='text-align: right;'>Admin</p>", unsafe_allow_html=True)

st.markdown("---")

# ------------------------------------------------------------------------------
# Page routing
# ------------------------------------------------------------------------------
if not st.session_state.logged_in:
    # HOME PAGE
    if st.session_state.page == 'home':
        st.markdown("<h1 style='text-align: center; margin-bottom: 2rem;'>Welcome to QuickQ</h1>", unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            <div class='custom-card'>
                <div class='portal-icon'>👨‍🎓</div>
                <h3>Student Portal</h3>
                <p>Login with your roll number</p>
            </div>
            """, unsafe_allow_html=True)
            # Adding login-btn class to the button container
            with st.container():
                st.markdown('<div class="login-btn">', unsafe_allow_html=True)
                if st.button("Open Student Portal", key="student_home", use_container_width=True):
                    st.session_state.page = 'student_login'
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class='custom-card'>
                <div class='portal-icon'>👩‍🏫</div>
                <h3>Admin Portal</h3>
                <p>Access management dashboard</p>
            </div>
            """, unsafe_allow_html=True)
            # Adding login-btn class to the button container
            with st.container():
                st.markdown('<div class="login-btn">', unsafe_allow_html=True)
                if st.button("Open Admin Portal", key="admin_home", use_container_width=True):
                    st.session_state.page = 'admin_login'
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
    
    # STUDENT LOGIN PAGE
    elif st.session_state.page == 'student_login':
        st.markdown("<h1 style='text-align: center; margin-bottom: 1rem;'>🔐 Student Login</h1>", unsafe_allow_html=True)
        
        st.markdown("""
        <div class='info-box'>
            <strong>📝 New Student?</strong> Just enter your details to register automatically.
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("student_login_form"):
            roll_number = st.text_input("Roll Number", placeholder="e.g., CS2024001")
            name = st.text_input("Full Name", placeholder="Enter your full name")
            password = st.text_input("Password", type="password", placeholder="Choose a password")
            
            col1, col2 = st.columns(2)
            with col1:
                department = st.selectbox("Select Department", st.session_state.departments)
            
            # Adding login-btn class to submit button
            st.markdown('<div class="login-btn">', unsafe_allow_html=True)
            submitted = st.form_submit_button("Login / Register", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            if submitted:
                if roll_number and name and password:
                    student = verify_student_login(roll_number, password)
                    
                    if student:
                        if student['is_defaulter']:
                            log_login_attempt(roll_number, name, 'blocked_defaulter')
                            st.markdown("""
                            <div class='defaulter-card'>
                                <h2>🚫 ACCESS DENIED</h2>
                                <p>You are marked as a DEFAULTER.</p>
                                <p>Please contact the admin to clear your dues.</p>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            log_login_attempt(roll_number, name, 'success')
                            st.session_state.logged_in = True
                            st.session_state.user_type = 'student'
                            st.session_state.user_data = student
                            st.session_state.selected_dept = department
                            st.session_state.page = 'student_dashboard'
                            st.rerun()
                    else:
                        if register_student(roll_number, name, password):
                            student = verify_student_login(roll_number, password)
                            log_login_attempt(roll_number, name, 'registered')
                            st.session_state.logged_in = True
                            st.session_state.user_type = 'student'
                            st.session_state.user_data = student
                            st.session_state.selected_dept = department
                            st.session_state.page = 'student_dashboard'
                            st.rerun()
                        else:
                            st.error("❌ Registration failed. Roll number might already exist.")
                else:
                    st.error("Please fill all fields")
        
        if st.button("← Back to Home"):
            st.session_state.page = 'home'
            st.rerun()
    
    # ADMIN LOGIN PAGE
    elif st.session_state.page == 'admin_login':
        st.markdown("<h1 style='text-align: center; margin-bottom: 1rem;'>👩‍🏫 Admin Portal</h1>", unsafe_allow_html=True)
        
        with st.form("admin_login_form"):
            admin_id = st.text_input("Admin ID", placeholder="Optional", key="admin_id_input")
            password = st.text_input("Password", type="password", placeholder="Enter password", key="admin_password_input")
            
            # Adding login-btn class to submit button
            st.markdown('<div class="login-btn">', unsafe_allow_html=True)
            submitted = st.form_submit_button("Login", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            if submitted:
                if password:
                    if verify_admin(password):
                        st.session_state.logged_in = True
                        st.session_state.user_type = 'admin'
                        st.session_state.user_data = {'name': 'Administrator', 'id': admin_id if admin_id else 'Admin'}
                        st.session_state.page = 'admin_dashboard'
                        st.rerun()
                    else:
                        st.error("❌ Invalid password")
                else:
                    st.error("Please enter the password")
        
        if st.button("← Back to Home"):
            st.session_state.page = 'home'
            st.rerun()

else:
    # STUDENT DASHBOARD
    if st.session_state.user_type == 'student':
        student = st.session_state.user_data
        dept = st.session_state.selected_dept
        q = get_queue_state(dept)
        
        if check_is_defaulter(student['roll_number']):
            logout()
            st.warning("You have been marked as defaulter. Session ended.")
            st.stop()
        
        current_token = get_student_current_token(student['roll_number'], dept)
        my_token = current_token[0] if current_token else None
        
        st.markdown(f"<h1>👋 Welcome, {student['name']}</h1>", unsafe_allow_html=True)
        
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("🚪 Logout", use_container_width=True):
                logout()
        
        st.markdown(f"<h2>{dept}</h2>", unsafe_allow_html=True)
        
        if q:
            tokens_left = 80 - q['total_issued']
            st.markdown(f"""
            <div class='token-counter'>
                🎟️ Tokens Available: {tokens_left}/80
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("<p class='stat-label'>Current serving</p>", unsafe_allow_html=True)
            st.markdown(f"<div class='token-badge'>{q['current']}</div>", unsafe_allow_html=True)
        
        if q and q['total_issued'] >= 80 and not my_token:
            st.markdown("""
            <div class='capacity-full'>
                🚫 SORRY!<br>
                Maximum capacity of 80 students reached.<br>
                No more tokens can be issued today.
            </div>
            """, unsafe_allow_html=True)
        
        elif not my_token:
            if dept == 'Submission' and st.session_state.selected_subject is None:
                st.markdown("<h3>Select Subject for Submission</h3>", unsafe_allow_html=True)
                
                cols = st.columns(3)
                subjects = st.session_state.submission_subjects
                
                for i, subject in enumerate(subjects):
                    with cols[i % 3]:
                        if st.button(f"📚 {subject}", key=f"subj_{subject}", use_container_width=True):
                            st.session_state.selected_subject = subject
                            st.rerun()
            
            elif dept != 'Submission' or st.session_state.selected_subject is not None:
                if dept == 'Submission' and st.session_state.selected_subject:
                    st.markdown(f"""
                    <div style='background: #1e293b; color: white; padding: 0.8rem; border-radius: 2rem; text-align: center; margin-bottom: 1rem; border: 1px solid #ffffff;'>
                        📚 Selected Subject: <strong style='color: white;'>{st.session_state.selected_subject}</strong>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.markdown("<h3>Select Time Slot</h3>", unsafe_allow_html=True)
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown(f"""
                    <div class='slot-card'>
                        🕐 Slot 1
                        <div class='slot-time'>{st.session_state.time_slots['Slot 1']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button("Select Slot 1", key="slot1", use_container_width=True):
                        new_token = get_next_token_number(dept)
                        if new_token:
                            subject_value = st.session_state.selected_subject if dept == 'Submission' else None
                            save_token(
                                student['roll_number'],
                                student['name'],
                                new_token,
                                dept,
                                subject_value,
                                'Slot 1'
                            )
                            st.session_state.selected_subject = None
                            st.rerun()
                        else:
                            st.error("No more tokens available!")
                
                with col2:
                    st.markdown(f"""
                    <div class='slot-card'>
                        🕑 Slot 2
                        <div class='slot-time'>{st.session_state.time_slots['Slot 2']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button("Select Slot 2", key="slot2", use_container_width=True):
                        new_token = get_next_token_number(dept)
                        if new_token:
                            subject_value = st.session_state.selected_subject if dept == 'Submission' else None
                            save_token(
                                student['roll_number'],
                                student['name'],
                                new_token,
                                dept,
                                subject_value,
                                'Slot 2'
                            )
                            st.session_state.selected_subject = None
                            st.rerun()
                        else:
                            st.error("No more tokens available!")
                
                with col3:
                    st.markdown(f"""
                    <div class='slot-card'>
                        🕒 Slot 3
                        <div class='slot-time'>{st.session_state.time_slots['Slot 3']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button("Select Slot 3", key="slot3", use_container_width=True):
                        new_token = get_next_token_number(dept)
                        if new_token:
                            subject_value = st.session_state.selected_subject if dept == 'Submission' else None
                            save_token(
                                student['roll_number'],
                                student['name'],
                                new_token,
                                dept,
                                subject_value,
                                'Slot 3'
                            )
                            st.session_state.selected_subject = None
                            st.rerun()
                        else:
                            st.error("No more tokens available!")
    
    # ADMIN DASHBOARD
    elif st.session_state.user_type == 'admin':
        admin = st.session_state.user_data
        
        st.markdown(f"<h1>👋 Welcome, Admin</h1>", unsafe_allow_html=True)
        
        # Section Dropdown - EXACT ORDER
        st.markdown("<h3>Select Section to Manage</h3>", unsafe_allow_html=True)
        section = st.selectbox(
            "Select Section",
            ["Submission", "Student Section", "Accounts Section", "Canteen", "Bus Line"],
            key="admin_section_select",
            help="Choose the section you want to manage"
        )
        
        st.session_state.admin_selected_section = section
        dept = section
        
        st.markdown(f"<h3>Currently Managing: {dept}</h3>", unsafe_allow_html=True)
        
        q = get_queue_state(dept)
        
        # Queue Control Section
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Current Token", q['current'])
        with col2:
            st.metric("Last Token", q['last'])
        with col3:
            st.metric("Total Issued", f"{q['total_issued']}/80")
        with col4:
            status = "Paused" if q['paused'] else "Running"
            st.metric("Status", status)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("Next Token", use_container_width=True):
                if update_current_token(dept):
                    st.success("Moved to next token!")
                    st.rerun()
                else:
                    st.warning("No more tokens in queue!")
        
        with col2:
            if q['paused']:
                if st.button("Resume Queue", use_container_width=True):
                    toggle_queue_pause(dept, False)
                    st.rerun()
            else:
                if st.button("Pause Queue", use_container_width=True):
                    toggle_queue_pause(dept, True)
                    st.rerun()
        
        with col3:
            if st.button("Refresh", use_container_width=True):
                st.rerun()
        
        st.markdown("---")
        
        # For Submission section, show subject dropdown
        if dept == "Submission":
            st.markdown("<h3>Filter by Subject</h3>", unsafe_allow_html=True)
            admin_selected_subject = st.selectbox(
                "Select Subject to Filter",
                ["All"] + st.session_state.submission_subjects,
                key="admin_subject_filter"
            )
            st.session_state.admin_selected_subject = admin_selected_subject if admin_selected_subject != "All" else None
        else:
            st.session_state.admin_selected_subject = None
        
        # Admin Tabs
        tab1, tab2, tab3, tab4 = st.tabs(["Queue Status", "Defaulters Management", "View Records", "Login History"])
        
        with tab1:
            st.subheader(f"Current Queue Status - {dept}")
            
            conn = get_db_connection()
            c = conn.cursor()
            
            if dept == "Submission" and st.session_state.admin_selected_subject:
                c.execute('''SELECT token_number, student_name, subject, slot, issued_time 
                            FROM tokens 
                            WHERE department = ? AND status = 'pending' AND token_number > ? AND subject = ?
                            ORDER BY token_number ASC''', (dept, q['current'], st.session_state.admin_selected_subject))
            else:
                c.execute('''SELECT token_number, student_name, subject, slot, issued_time 
                            FROM tokens 
                            WHERE department = ? AND status = 'pending' AND token_number > ?
                            ORDER BY token_number ASC''', (dept, q['current']))
            
            waiting_tokens = c.fetchall()
            conn.close()
            
            if waiting_tokens:
                for token in waiting_tokens:
                    subject_display = f"({token[2]})" if token[2] else ""
                    st.info(f"Token #{token[0]} - {token[1]} {subject_display} - {token[3]}")
            else:
                st.success("No tokens waiting in queue")
        
        with tab2:
            st.subheader("Manage Defaulters")
            
            with st.expander("Add Multiple Students to Defaulter List"):
                st.markdown("""
                <p>Enter student names (comma-separated or one per line):</p>
                """, unsafe_allow_html=True)
                
                names_input = st.text_area(
                    "Student Names",
                    placeholder="Example: Rahul, Priya, Amit\nOR\nRahul\nPriya\nAmit",
                    height=100,
                    key="multiple_names"
                )
                
                reason = st.text_input("Reason for adding to defaulter list", key="bulk_reason")
                
                if st.button("Add Multiple Students to Defaulters"):
                    if names_input and reason:
                        success, message = add_multiple_to_defaulters(names_input, reason, admin.get('id', 'admin'))
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
                    else:
                        st.error("Please enter student names and reason")
            
            with st.expander("Add Single Student to Defaulter List"):
                col1, col2 = st.columns(2)
                with col1:
                    roll_to_add = st.text_input("Roll Number", key="add_roll")
                with col2:
                    reason_single = st.text_input("Reason", key="reason_single")
                
                if st.button("Add Single Student"):
                    if roll_to_add and reason_single:
                        if add_to_defaulters(roll_to_add, reason_single, admin.get('id', 'admin')):
                            st.success(f"Added {roll_to_add} to defaulters list!")
                            st.rerun()
                        else:
                            st.error("Student not found!")
            
            with st.expander("Remove Student from Defaulter List"):
                roll_to_remove = st.text_input("Roll Number", key="remove_roll")
                if st.button("Remove from Defaulters"):
                    if roll_to_remove:
                        if remove_from_defaulters(roll_to_remove, admin.get('id', 'admin')):
                            st.success(f"Removed {roll_to_remove} from defaulters list!")
                            st.rerun()
                        else:
                            st.error("Student not found in defaulters list!")
            
            st.subheader("Current Defaulters List")
            defaulters = get_all_defaulters()
            if defaulters:
                for defaulter in defaulters:
                    st.warning(f"{defaulter[0]} - {defaulter[1]} (Added: {defaulter[2]}) - Reason: {defaulter[3]}")
            else:
                st.success("No defaulters in the list")
        
        with tab3:
            st.subheader(f"Token Records - {dept}")
            
            col1, col2 = st.columns(2)
            with col1:
                if dept == "Submission":
                    filter_subject = st.selectbox(
                        "Filter by Subject", 
                        ["All"] + st.session_state.submission_subjects,
                        key="filter_subject_admin"
                    )
                else:
                    filter_subject = "All"
                    st.info("Subject filtering only available for Submission section")
            
            with col2:
                filter_status = st.selectbox(
                    "Filter by Status", 
                    ["All", "pending", "completed"],
                    key="filter_status_admin"
                )
            
            conn = get_db_connection()
            query = "SELECT * FROM tokens WHERE department = ?"
            params = [dept]
            
            if dept == "Submission" and filter_subject != "All":
                query += " AND subject = ?"
                params.append(filter_subject)
            
            if filter_status != "All":
                query += " AND status = ?"
                params.append(filter_status)
            
            query += " ORDER BY issued_time DESC LIMIT 50"
            
            c = conn.cursor()
            c.execute(query, params)
            records = c.fetchall()
            conn.close()
            
            if records:
                for record in records:
                    with st.container():
                        col1, col2, col3 = st.columns([2, 3, 2])
                        with col1:
                            st.write(f"Token #{record[1]}")
                        with col2:
                            subject_display = record[4] if record[4] else "No Subject"
                            st.write(f"{record[3]} - {subject_display}")
                        with col3:
                            status_color = "🟢" if record[8] == "completed" else "🟡"
                            st.write(f"{status_color} {record[8]}")
                        st.caption(f"Time: {record[6]}")
                        st.divider()
            else:
                st.info("No records found")
        
        with tab4:
            st.subheader("Login History")
            login_history = get_login_history()
            
            if login_history:
                for login in login_history:
                    with st.container():
                        col1, col2, col3 = st.columns([2, 3, 2])
                        with col1:
                            st.write(login[1])
                        with col2:
                            st.write(login[2])
                        with col3:
                            status_color = "🟢" if login[4] == "success" else "🔴"
                            st.write(f"{status_color} {login[4]}")
                        st.caption(f"Time: {login[3]}")
                        st.divider()
            else:
                st.info("No login history found")
        
        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            logout()