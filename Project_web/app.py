# =========================================================
# Employee Attendance Web App
# Full version with Login, Logout, Home, Attendance & Dashboard
# =========================================================

from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps
import pyodbc

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # needed for sessions

# -------------------- SQL Connection --------------------
def get_conn():
    return pyodbc.connect(
        'DRIVER={SQL Server};'
        'SERVER=localhost\\SQLEXPRESS;'
        'DATABASE=EAMS_DB;'
        'Trusted_Connection=yes;'
    )
    from functools import wraps
from flask import abort

def get_current_user():
    return session.get('username')

def is_admin(username: str) -> bool:
    if not username:
        return False
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT 1
            FROM UserAccount ua
            JOIN UserRole ur ON ua.User_ID = ur.User_ID
            JOIN Role r ON ur.Role_ID = r.Role_ID
            WHERE ua.Username = ? AND r.Role_Code = 'ADM' AND ua.IsActive = 1
        """, (username,))
        return cur.fetchone() is not None

def admin_only(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        username = get_current_user()
        if not username:
            return redirect(url_for('login'))
        if not is_admin(username):
            abort(403)  # Forbidden
        return view(*args, **kwargs)
    return wrapper

    return pyodbc.connect(
        'DRIVER={SQL Server};'
        'SERVER=localhost\\SQLEXPRESS;'  # Change if your SQL Server name is different
        'DATABASE=EAMS_DB;'
        'Trusted_Connection=yes;'
    )

# -------------------- LOGIN --------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.User_ID, u.Password_Hash, 
                       ISNULL(r.Role_Name, 'Employee') AS RoleName
                FROM UserAccount u
                LEFT JOIN UserRole ur ON u.User_ID = ur.User_ID
                LEFT JOIN Role r ON ur.Role_ID = r.Role_ID
                WHERE u.Username = ? AND u.IsActive = 1
            """, (username,))
            row = cursor.fetchone()

        if row and row[1] == password:
            session['username'] = username
            session['role'] = row[2]  # <-- store the user's role in session

            if session['role'].lower() == 'administrator' or session['role'].lower() == 'admin':
                flash('Admin login successful!', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Employee login successful!', 'success')
                return redirect(url_for('home'))
        else:
            flash('Invalid username or password', 'danger')

    return render_template('login.html')


# -------------------- LOGOUT --------------------
@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('Logged out successfully!', 'info')
    return redirect(url_for('login'))


# -------------------- HOME PAGE --------------------
@app.route('/')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))

    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT TOP 10 Employee_Name, Position, Join_Date FROM Employee;")
        employees = cursor.fetchall()

    return render_template('index.html', employees=employees)


# -------------------- ATTENDANCE PAGE --------------------
from datetime import datetime

@app.route('/attendance')
def attendance():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    month_now = datetime.now().strftime("%Y-%m")

    with get_conn() as conn:
        cursor = conn.cursor()

        # 🔹 1️⃣ Find logged-in employee
        cursor.execute("""
            SELECT e.Employee_ID, e.Employee_Name
            FROM UserAccount u
            JOIN Employee e ON u.Employee_ID = e.Employee_ID
            WHERE u.Username = ? AND u.IsActive = 1
        """, (username,))
        emp = cursor.fetchone()

        if not emp:
            return render_template('attendance.html', message="Employee record not found.")

        emp_id, emp_name = emp

        # 🔹 2️⃣ Fetch current month's attendance records
        cursor.execute("""
            SELECT FORMAT(a.Att_Date, 'yyyy-MM-dd') AS Att_Date,
                   a.Status,
                   ISNULL(a.Remark, '-') AS Remark
            FROM Attendance a
            WHERE a.Employee_ID = ? AND FORMAT(a.Att_Date, 'yyyy-MM') = ?
            ORDER BY a.Att_Date
        """, (emp_id, month_now))
        records = cursor.fetchall()

        # 🔹 3️⃣ Count summary
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN Status = 'Present' THEN 1 ELSE 0 END),
                SUM(CASE WHEN Status = 'Absent' THEN 1 ELSE 0 END)
            FROM Attendance
            WHERE Employee_ID = ? AND FORMAT(Att_Date, 'yyyy-MM') = ?
        """, (emp_id, month_now))
        summary = cursor.fetchone()
        present = summary[0] or 0
        absent = summary[1] or 0

    return render_template(
        'attendance.html',
        name=emp_name,
        month=month_now,
        records=records,
        present=present,
        absent=absent
    )


# -------------------- DASHBOARD PAGE --------------------
from datetime import datetime, timedelta


@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    current_month = datetime.now().strftime("%Y-%m")

    with get_conn() as conn:
        cursor = conn.cursor()

        # 1️⃣ Get Employee ID and Name
        cursor.execute("""
            SELECT e.Employee_ID, e.Employee_Name
            FROM UserAccount u
            JOIN Employee e ON u.Employee_ID = e.Employee_ID
            WHERE u.Username = ? AND u.IsActive = 1
        """, (username,))
        emp = cursor.fetchone()
        if not emp:
            return render_template('dashboard.html', message="Employee not found.")
        emp_id, emp_name = emp

        # 2️⃣ Function to calculate salary per month
        def calculate_salary(emp_id, month):
            cursor.execute("""
                SELECT Basic_Salary, Allowance, Deduction_Per_Absent
                FROM SalaryStructure
                WHERE Employee_ID = ?
            """, (emp_id,))
            s = cursor.fetchone()
            if not s:
                return 0
            basic, allowance, deduction = s
            total_fixed = basic + allowance

            cursor.execute("""
                SELECT 
                    SUM(CASE WHEN Status='Present' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN Status='Absent' THEN 1 ELSE 0 END)
                FROM Attendance
                WHERE Employee_ID = ? AND FORMAT(Att_Date, 'yyyy-MM') = ?
            """, (emp_id, month))
            a = cursor.fetchone()
            present = a[0] or 0
            absent = a[1] or 0

            daily_rate = total_fixed / 30
            total = (present * daily_rate) - (absent * deduction)
            return round(total, 2)

        # 3️⃣ Generate last 6 months (including current)
        months = []
        today = datetime.now().replace(day=1)
        for i in range(5, -1, -1):
            month = (today - timedelta(days=i * 30)).strftime("%Y-%m")
            months.append(month)

        # 4️⃣ Attendance data for last 6 months
        attendance_labels = []
        present_values = []
        absent_values = []
        salary_values = []

        for month in months:
            cursor.execute("""
                SELECT 
                    SUM(CASE WHEN Status='Present' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN Status='Absent' THEN 1 ELSE 0 END)
                FROM Attendance
                WHERE Employee_ID = ? AND FORMAT(Att_Date, 'yyyy-MM') = ?
            """, (emp_id, month))
            data = cursor.fetchone()
            present = data[0] or 0
            absent = data[1] or 0
            attendance_labels.append(month)
            present_values.append(present)
            absent_values.append(absent)

            salary_values.append(calculate_salary(emp_id, month))

        # 5️⃣ Calculate salary improvement %
        current_salary = salary_values[-1] if salary_values else 0
        prev_salary = salary_values[-2] if len(salary_values) > 1 else 0
        salary_improvement = 0
        if prev_salary > 0:
            salary_improvement = round(((current_salary - prev_salary) / prev_salary) * 100, 2)

    return render_template(
        'dashboard.html',
        name=emp_name,
        attendance_labels=attendance_labels,
        present_values=present_values,
        absent_values=absent_values,
        salary_values=salary_values,
        current_salary=current_salary,
        salary_improvement=salary_improvement
    )

# -------------------- SALARY PAGE --------------------
from datetime import datetime


@app.route('/salary')
def salary():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    month_now = datetime.now().strftime("%Y-%m")

    with get_conn() as conn:
        cursor = conn.cursor()

        # 1️⃣ Get Employee ID based on logged-in username
        cursor.execute("""
            SELECT e.Employee_ID, e.Employee_Name
            FROM UserAccount u
            JOIN Employee e ON u.Employee_ID = e.Employee_ID
            WHERE u.Username = ? AND u.IsActive = 1
        """, (username,))
        emp = cursor.fetchone()

        if not emp:
            return render_template('salary.html', message="Employee record not found.")
        
        emp_id, emp_name = emp

        # 2️⃣ Get salary info for this employee
        cursor.execute("""
            SELECT Basic_Salary, Allowance, Deduction_Per_Absent
            FROM SalaryStructure
            WHERE Employee_ID = ?
        """, (emp_id,))
        salary_info = cursor.fetchone()

        if not salary_info:
            return render_template('salary.html', message="No salary structure defined for this employee.")

        basic, allowance, deduction = salary_info

        # 3️⃣ Count attendance stats for current month
        cursor.execute("""
            SELECT 
                COUNT(*) AS TotalDays,
                SUM(CASE WHEN Status = 'Present' THEN 1 ELSE 0 END) AS PresentDays,
                SUM(CASE WHEN Status = 'Absent' THEN 1 ELSE 0 END) AS AbsentDays
            FROM Attendance
            WHERE Employee_ID = ? AND FORMAT(Att_Date, 'yyyy-MM') = ?
        """, (emp_id, month_now))
        stats = cursor.fetchone()

        total_days = stats[0] or 0
        present = stats[1] or 0
        absent = stats[2] or 0

        # 4️⃣ Calculate daily rate
        daily_rate = (basic + allowance) / 30  # assuming 30-day month
        deduction_total = absent * deduction

        # 5️⃣ Calculate total payable salary
        total_pay = (present * daily_rate) - deduction_total
        total_pay = round(total_pay, 2)

    return render_template(
        'salary.html',
        name=emp_name,
        month=month_now,
        basic=basic,
        allowance=allowance,
        deduction=deduction,
        present=present,
        absent=absent,
        total_days=total_days,
        daily_rate=round(daily_rate, 2),
        total_pay=total_pay
    )
# -------------------- LEAVE APPLICATION --------------------
from datetime import date

@app.route('/leave', methods=['GET', 'POST'])
def leave():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']

    with get_conn() as conn:
        cursor = conn.cursor()

        # 1️⃣ Get logged-in employee ID and name
        cursor.execute("""
            SELECT e.Employee_ID, e.Employee_Name
            FROM UserAccount u
            JOIN Employee e ON u.Employee_ID = e.Employee_ID
            WHERE u.Username = ? AND u.IsActive = 1
        """, (username,))
        emp = cursor.fetchone()
        if not emp:
            return render_template('leave.html', message="Employee not found.")
        emp_id, emp_name = emp

        # 2️⃣ Handle form submission
        if request.method == 'POST':
            leave_type = request.form['leave_type']
            start_date = request.form['start_date']
            end_date = request.form['end_date']
            reason = request.form['reason']

            cursor.execute("""
                INSERT INTO LeaveRecord (Employee_ID, LeaveType_ID, Start_Date, End_Date, Reason, Approval_Status)
                VALUES (?, ?, ?, ?, ?, 'Pending')
            """, (emp_id, leave_type, start_date, end_date, reason))
            conn.commit()
            flash("Leave request submitted successfully!", "success")

        # 3️⃣ Fetch available leave types
        cursor.execute("SELECT LeaveType_ID, Type_Name FROM LeaveType")
        leave_types = cursor.fetchall()

        # 4️⃣ Fetch this employee’s past leave requests
        cursor.execute("""
            SELECT FORMAT(Start_Date, 'yyyy-MM-dd'), FORMAT(End_Date, 'yyyy-MM-dd'), Reason, Approval_Status
            FROM LeaveRecord
            WHERE Employee_ID = ?
            ORDER BY Leave_ID DESC
        """, (emp_id,))
        leave_history = cursor.fetchall()

    return render_template(
        'leave.html',
        name=emp_name,
        leave_types=leave_types,
        leave_history=leave_history
    )
# -------------------- ADMIN DASHBOARD --------------------
@app.route('/admin/dashboard')
@admin_only
def admin_dashboard():
    conn = get_conn()
    cursor = conn.cursor()

    # Total employees
    cursor.execute("SELECT COUNT(*) FROM Employee;")
    total_employees = cursor.fetchone()[0] or 0

    # Pending leaves
    cursor.execute("SELECT COUNT(*) FROM LeaveRecord WHERE Approval_Status = 'Pending';")
    pending_leaves = cursor.fetchone()[0] or 0

    # Salary Summary — Calculate per employee then average
    cursor.execute("""
        SELECT 
            e.Employee_Name,
            ISNULL(e.Base_Salary, 0) AS Base_Salary,
            SUM(CASE WHEN a.Status = 'Present' THEN 1 ELSE 0 END) AS PresentDays,
            COUNT(a.Attendance_ID) AS TotalDays
        FROM Employee e
        LEFT JOIN Attendance a ON e.Employee_ID = a.Employee_ID
            AND MONTH(a.Att_Date) = MONTH(GETDATE())
            AND YEAR(a.Att_Date) = YEAR(GETDATE())
        GROUP BY e.Employee_Name, e.Base_Salary;
    """)

    salary_rows = cursor.fetchall()
    total_salaries = 0
    employee_count = 0

    for row in salary_rows:
        base_salary = float(row[1] or 0)  # Convert Decimal → float
        present = float(row[2] or 0)
        total = float(row[3] or 0)

        if total > 0:
            final_salary = (present / total) * base_salary
        else:
            final_salary = 0

        total_salaries += final_salary
        employee_count += 1

    avg_salary = round(total_salaries / employee_count, 2) if employee_count > 0 else 0

    conn.close()
    return render_template(
        'admin_dashboard.html',
        total_employees=total_employees,
        pending_leaves=pending_leaves,
        avg_salary=avg_salary
    )

# -------------------- ADMIN: Manage Employees --------------------

@app.route('/admin/manage-employees')
@admin_only
def admin_manage_employees():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Employee_ID, Employee_Name, Position, Join_Date
        FROM Employee
        ORDER BY Employee_Name;
    """)
    employees = cursor.fetchall()
    conn.close()
    return render_template('admin_employees.html', employees=employees)


# -------------------- ADMIN: Add Employee --------------------

@app.route('/admin/employees/add', methods=['GET', 'POST'])
@admin_only
def admin_add_employee():
    if request.method == 'POST':
        name = request.form['name']
        position = request.form['position']
        join_date = request.form['join_date']

        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Employee (Employee_Name, Position, Join_Date)
            VALUES (?, ?, ?);
        """, (name, position, join_date))
        conn.commit()
        conn.close()

        flash('Employee added successfully!', 'success')
        return redirect(url_for('admin_manage_employees'))

    # Simple add form
    return '''
    <div style="max-width:500px;margin:auto;padding-top:40px;">
        <h3>Add Employee</h3>
        <form method="POST">
            <input name="name" class="form-control mb-2" placeholder="Employee Name" required>
            <input name="position" class="form-control mb-2" placeholder="Position" required>
            <input type="date" name="join_date" class="form-control mb-2" required>
            <button class="btn btn-primary w-100">Save</button>
        </form>
    </div>
    '''


# -------------------- ADMIN: Delete Employee --------------------

@app.route('/admin/employees/delete/<int:emp_id>')
@admin_only
def admin_delete_employee(emp_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM Employee WHERE Employee_ID = ?", (emp_id,))
    conn.commit()
    conn.close()
    flash('Employee deleted successfully!', 'info')
    return redirect(url_for('admin_manage_employees'))


# -------------------- ADMIN: EMPLOYEES LIST --------------------
@app.route('/admin/employees/manage')
@admin_only
def admin_employees_manage():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT e.Employee_ID, e.Employee_Name, d.Department_Name, e.Position,
                   CONVERT(varchar(10), e.Join_Date, 120) AS JoinDate
            FROM Employee e
            LEFT JOIN Department d ON e.Department_ID = d.Department_ID
            ORDER BY e.Employee_Name
        """)
        employees = cur.fetchall()
    return render_template('admin_employees.html', employees=employees)
# -------------------- ADMIN: SALARY MANAGEMENT --------------------
# ---------- Admin: Salary (Monthly Overview) ----------
@app.route('/admin/salary')
@admin_only
def admin_salary():
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                e.Employee_Name,
                e.Base_Salary,
                COUNT(a.Attendance_ID) AS Total_Working_Days,
                SUM(CASE WHEN a.Status = 'Present' THEN 1 ELSE 0 END) AS Present_Days,
                CAST(
                    CASE 
                        WHEN COUNT(a.Attendance_ID) = 0 THEN 0
                        ELSE (SUM(CASE WHEN a.Status = 'Present' THEN 1 ELSE 0 END) * 1.0 / COUNT(a.Attendance_ID)) * e.Base_Salary
                    END AS DECIMAL(10,2)
                ) AS Calculated_Salary
            FROM Employee e
            LEFT JOIN Attendance a ON e.Employee_ID = a.Employee_ID
            GROUP BY e.Employee_Name, e.Base_Salary
            ORDER BY e.Employee_Name;
        """)
        salary_data = cursor.fetchall()

    return render_template("admin_salary.html", salary_data=salary_data)

# -------------------- ADMIN: LEAVE APPROVALS --------------------
@app.route('/admin/leaves')
@admin_only
def admin_leaves():
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                lr.Leave_ID,
                e.Employee_Name,
                lr.Start_Date,
                lr.End_Date,
                lr.Reason,
                lr.Approval_Status,
                lr.Approved_By
            FROM LeaveRecord lr
            JOIN Employee e ON lr.Employee_ID = e.Employee_ID
            ORDER BY lr.Start_Date DESC;
        """)
        leaves = cursor.fetchall()

    return render_template('admin_leaves.html', leaves=leaves)


# =========================================================
# ADMIN LEAVES PAGE — Approve or Reject leaves
@app.route('/admin/leave/approve/<int:leave_id>')
@admin_only
def approve_leave(leave_id):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE LeaveRecord
            SET Approval_Status = 'Approved', Approved_By = ?
            WHERE Leave_ID = ?;
        """, (session.get('username'), leave_id))
        conn.commit()
    flash('Leave approved successfully.', 'success')
    return redirect(url_for('admin_leaves'))


@app.route('/admin/leave/reject/<int:leave_id>')
@admin_only
def reject_leave(leave_id):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE LeaveRecord
            SET Approval_Status = 'Rejected', Approved_By = ?
            WHERE Leave_ID = ?;
        """, (session.get('username'), leave_id))
        conn.commit()
    flash('Leave rejected.', 'danger')
    return redirect(url_for('admin_leaves'))

# -------------------- Run App --------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)



