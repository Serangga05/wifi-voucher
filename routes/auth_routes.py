from flask import Blueprint, render_template, request, redirect, session
from database import users_collection
import bcrypt

auth = Blueprint('auth', __name__)

# REGISTER
@auth.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        name = request.form['name']
        whatsapp = request.form['whatsapp']
        password = request.form['password']

        # cek nama atau whatsapp sudah digunakan
        existing_user = users_collection.find_one({
            "$or": [
                {"name": name},
                {"whatsapp": whatsapp}
            ]
        })

        if existing_user:
            return "Nama atau WhatsApp sudah digunakan"

        # hash password
        hashed_password = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt()
        )

        # simpan user
        users_collection.insert_one({

            "name": name,

            "whatsapp": whatsapp,

            "password": hashed_password,

            "role": "user"
        })

        return redirect('/login')

    return render_template('register.html')


# LOGIN
@auth.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        whatsapp = request.form['whatsapp']
        password = request.form['password']

        # cari user
        user = users_collection.find_one({
            "whatsapp": whatsapp
        })

        # cek password
        if user and bcrypt.checkpw(
            password.encode('utf-8'),
            user['password']
        ):

            session['user_id'] = str(user['_id'])
            session['user_name'] = user['name']

            return redirect('/')

        return "Login gagal"

    return render_template('login.html')


# LOGOUT
@auth.route('/logout')
def logout():

    session.clear()

    return redirect('/login')