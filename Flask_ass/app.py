from flask import Flask, redirect, url_for, render_template, request, session
from datetime import timedelta
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
import os
import random
import string

app = Flask(__name__)
sio = SocketIO(app)

# Configuration
app.secret_key = os.getenv('SECRET_KEY', ''.join(random.choices(string.ascii_letters, k=16)))
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///users.sqlite3')
app.config['SQLALCHEMY_BINDS'] = {
    'db1': os.getenv('DB1_URL', 'sqlite:///users1.sqlite3'),
    'db2': os.getenv('DB2_URL', 'sqlite:///users2.sqlite3')
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.permanent_session_lifetime = timedelta(minutes=15)

db = SQLAlchemy(app)

# Initialize login count
current_login_count = 0

# Database models
class Users(db.Model):
    __bind_key__ = 'db1'
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    usr_name = db.Column(db.String(100), unique=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))  # Storing plaintext password (insecure practice)

class StudentDatabase(db.Model):
    __bind_key__ = 'db2'
    __tablename__ = 'student_database'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    surname = db.Column(db.String(255))
    fathers_name = db.Column(db.String(255))
    age = db.Column(db.Integer)
    email = db.Column(db.String(255))

# Routes
@app.route("/", methods=['POST','GET'])
def home():
    if 'found_user' in session:
        return render_template('home.html')
    else:
        return redirect(url_for('login'))

@app.route("/login", methods=["POST", "GET"])
def login():
    global current_login_count
    if request.method == "POST":
        session.permanent = True
        email = request.form["email"]
        password = request.form["password"]

        found_user = Users.query.filter_by(email=email).first()

        if found_user and found_user.password == password:
            session['found_user'] = found_user.usr_name
            current_login_count += 1  # Increment login count
            # Emit the updated login count to all connected clients
            sio.emit('login_count', {'count': current_login_count})
            return redirect(url_for('home'))
        else:
            return redirect(url_for('sign_up'))
    else:
        if "found_user" in session:
            return redirect(url_for("home"))
        return render_template("login.html")

@app.route("/logout", methods=['POST', 'GET'])
def logout():
    global current_login_count
    if 'found_user' in session:
        session.pop('found_user', None)
        current_login_count -= 1  # Decrement login count on logout
        # Emit the updated login count to all connected clients
        sio.emit('login_count', {'count': current_login_count})
    return redirect(url_for('login'))

# Socket.IO event handlers
@sio.on('connect')
def on_connect():
    print("Client connected")
    # Emit the current login count when a new client connects
    sio.emit('login_count', {'count': current_login_count})

@sio.on('disconnect')
def on_disconnect():
    print("Client disconnected")

# Additional routes (e.g., sign up, account management, database view)
@app.route("/sign_up", methods=["POST", "GET"])
def sign_up():
    if request.method == "POST":
        usr_email = request.form["email"]
        usr_password = request.form["password"]
        usr_name = request.form["usr_name"]

        existing_user = Users.query.filter((Users.email == usr_email) | (Users.usr_name == usr_name)).first()

        if existing_user is None:
            usr = Users(password=usr_password, usr_name=usr_name, email=usr_email)
            db.session.add(usr)
            try:
                db.session.commit()  # Commit the changes to the database
                session['found_user'] = usr_name
                return redirect(url_for('home'))
            except Exception as e:
                db.session.rollback()  # Rollback in case of an error
                print(f"Error adding user: {e}")
                return "Error occurred while adding user."
        else:
            return redirect(url_for('login'))
    return render_template("sign_up.html")

@app.route('/account', methods=['POST', 'GET'])
def account():
    if 'found_user' not in session:
        return redirect(url_for('login'))
    
    user = Users.query.filter_by(usr_name=session['found_user']).first()

    if request.method == 'POST':
        if 'update' in request.form:
            new_username = request.form['usr_name']
            new_password = request.form['password']

            # Update user details
            if new_username:
                user.usr_name = new_username
                session['found_user'] = new_username 
            if new_password:
                user.password = new_password

            db.session.commit()
            return redirect(url_for('account'))

        elif 'delete' in request.form:
            db.session.delete(user)
            db.session.commit()
            session.pop('found_user', None)
            return redirect(url_for('sign_up'))

    return render_template('account.html', user=user)

@app.route('/database', methods=['POST', 'GET'])
def database_view():
    if 'found_user' is not None:
        students = StudentDatabase.query.all()

        if request.method == 'POST':
            if 'add' in request.form:
                name = request.form['name']
                surname = request.form['surname']
                fathers_name = request.form['fathers_name']
                age = int(request.form['age'])
                email = request.form['email']

                new_student = StudentDatabase(name, surname, fathers_name, age, email)
                db.session.add(new_student)
                db.session.commit()

            elif 'edit' in request.form:
                student_id = request.form['student_id']
                student = StudentDatabase.query.get(student_id)
                if student:
                    student.name = request.form['name']
                    student.surname = request.form['surname']
                    student.fathers_name = request.form['fathers_name']
                    student.age = int(request.form['age'])
                    student.email = request.form['email']
                    db.session.commit()

            elif 'delete' in request.form:
                student_id = request.form['student_id']
                student = StudentDatabase.query.get(student_id)
                if student:
                    db.session.delete(student)
                    db.session.commit()

            return redirect(url_for('database_view'))

        return render_template('database.html', students=students)
    else:
        return redirect('login')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    sio.run(app, debug=True)
