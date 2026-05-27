from flask import Blueprint, render_template, request, redirect, session
from bson.objectid import ObjectId
import bcrypt
from datetime import datetime, timedelta
import pandas as pd
from flask import send_file
import io

from database import (
    locations_collection,
    packages_collection,
    vouchers_collection,
    users_collection,
    transactions_collection
)

admin = Blueprint('admin', __name__)

# =========================
# ADMIN AUTH CHECK
# =========================
def admin_required():

    if 'admin_id' not in session:
        return False

    return True

# =========================
# ADMIN LOGIN
# =========================
@admin.route('/admin/login', methods=['GET', 'POST'])
def admin_login():

    if request.method == 'POST':

        whatsapp = request.form['whatsapp']
        password = request.form['password']

        admin_user = users_collection.find_one({

            "whatsapp": whatsapp,

            "role": "admin"
        })

        if admin_user and bcrypt.checkpw(

            password.encode('utf-8'),

            admin_user['password'].encode('utf-8')

        ):

            session['admin_id'] = str(admin_user['_id'])

            session['admin_name'] = admin_user['name']

            return redirect('/admin/dashboard')

        return "Login admin gagal"

    return render_template('admin_login.html')

# =========================
# ADMIN LOGOUT
# =========================
@admin.route('/admin/logout')
def admin_logout():

    session.clear()

    return redirect('/admin/login')

# =========================
# ADMIN DASHBOARD
# =========================
@admin.route('/admin/dashboard')
def admin_dashboard():

    if not admin_required():
        return redirect('/admin/login')

    # =========================
    # TOTAL TRANSAKSI
    # =========================
    total_transactions = transactions_collection.count_documents({

        "payment_status": "PAID"
    })

    # =========================
    # VOUCHER READY
    # =========================
    total_voucher_ready = vouchers_collection.count_documents({

        "used": False
    })

    # =========================
    # VOUCHER SOLD
    # =========================
    total_voucher_sold = vouchers_collection.count_documents({

        "used": True
    })

    # =========================
    # AMBIL TRANSAKSI PAID
    # =========================
    paid_transactions = list(

        transactions_collection.find({

            "payment_status": "PAID"
        })

    )

    # =========================
    # TOTAL REVENUE
    # =========================
    total_revenue = 0

    # =========================
    # CHART REVENUE
    # =========================
    revenue_per_day = {}

    # =========================
    # PACKAGE TERLARIS
    # =========================
    package_sales = {}

    # =========================
    # LOOP TRANSAKSI
    # =========================
    for transaction in paid_transactions:

        # =========================
        # TOTAL REVENUE
        # =========================
        amount = transaction.get('amount', 0)

        total_revenue += amount

        # =========================
        # TANGGAL TRANSAKSI
        # =========================
        purchase_time = transaction.get('purchase_time')

        if purchase_time:

            day = purchase_time.strftime("%d/%m")

            if day not in revenue_per_day:

                revenue_per_day[day] = 0

            revenue_per_day[day] += amount

        # =========================
        # PACKAGE TERLARIS
        # =========================
        package_id = transaction.get('package_id')

        if package_id:

            try:

                package = packages_collection.find_one({

                    "_id": ObjectId(package_id)
                })

                if package:

                    package_name = package['name']

                    if package_name not in package_sales:

                        package_sales[package_name] = 0

                    package_sales[package_name] += 1

            except:

                pass

    # =========================
    # CHART DATA
    # =========================
    sorted_days = sorted(revenue_per_day.keys())

    chart_labels = sorted_days

    chart_values = [

        revenue_per_day[day]

        for day in sorted_days
    ]

    # =========================
    # PACKAGE TERLARIS
    # =========================
    top_package = None

    if package_sales:

        top_package = max(

            package_sales,

            key=package_sales.get
        )

    # =========================
    # RENDER TEMPLATE
    # =========================
    return render_template(

        'admin_dashboard.html',

        admin_name=session['admin_name'],

        total_transactions=total_transactions,

        total_voucher_ready=total_voucher_ready,

        total_voucher_sold=total_voucher_sold,

        chart_labels=chart_labels,

        chart_values=chart_values,

        total_revenue=total_revenue,

        top_package=top_package
    )

# =========================
# TRANSACTIONS
# =========================
@admin.route('/admin/transactions')
def admin_transactions():

    if not admin_required():
        return redirect('/admin/login')

    # =========================
    # PAGINATION
    # =========================
    page = request.args.get(
        'page',
        1,
        type=int
    )

    per_page = 10

    skip = (page - 1) * per_page

    # =========================
    # SEARCH
    # =========================
    search = request.args.get(
        'search',
        ''
    )

    query = {}

    # =========================
    # SEARCH USER NAME
    # =========================
    if search:

        users = list(

            users_collection.find({

                "name": {

                    "$regex": search,

                    "$options": "i"
                }
            })

        )

        user_ids = [

            str(user['_id'])

            for user in users
        ]

        query['user_id'] = {

            '$in': user_ids
        }

    # =========================
    # TOTAL DATA
    # =========================
    total_transactions = transactions_collection.count_documents(
        query
    )

    total_pages = (

        total_transactions + per_page - 1

    ) // per_page

    # =========================
    # GET DATA
    # =========================
    transactions = list(

        transactions_collection.find(query)

        .sort("purchase_time", -1)

        .skip(skip)

        .limit(per_page)
    )

    # =========================
    # LOOP DATA
    # =========================
    for transaction in transactions:

        # USER
        user = users_collection.find_one({

            "_id": ObjectId(
                transaction['user_id']
            )
        })

        transaction['user'] = user

        # PACKAGE
        package = packages_collection.find_one({

            "_id": ObjectId(
                transaction['package_id']
            )
        })

        transaction['package'] = package

        # LOCATION
        if package:

            location = locations_collection.find_one({

                "_id": ObjectId(
                    package['location_id']
                )
            })

            transaction['location'] = location

    return render_template(

        'admin_transactions.html',

        transactions=transactions,

        page=page,

        total_pages=total_pages,

        search=search
    )

# =========================
# EXPORT TRANSACTIONS EXCEL
# =========================
@admin.route('/admin/export-transactions')
def export_transactions():

    if not admin_required():
        return redirect('/admin/login')

    transactions = list(
        transactions_collection.find({

            "payment_status": "PAID"
        })
    )

    data = []

    for transaction in transactions:

        # USER
        user = users_collection.find_one({

            "_id": ObjectId(
                transaction['user_id']
            )
        })

        # PACKAGE
        package = packages_collection.find_one({

            "_id": ObjectId(
                transaction['package_id']
            )
        })

        # LOCATION
        location_name = "-"

        package_name = "-"

        if package:

            package_name = package['name']

            location = locations_collection.find_one({

                "_id": ObjectId(
                    package['location_id']
                )
            })

            if location:

                location_name = location['name']

        # TANGGAL
        purchase_time = transaction.get(
            'purchase_time'
        )

        if purchase_time:

            tanggal = purchase_time.strftime(
                "%d/%m/%Y %H:%M"
            )

        else:

            tanggal = "-"

        # DATA
        data.append({

            "Nama User":
            user['name'] if user else "-",

            "WhatsApp":
            user['whatsapp'] if user else "-",

            "Lokasi":
            location_name,

            "Package":
            package_name,

            "Harga":
            transaction.get('amount', 0),

            "Status":
            transaction.get(
                'payment_status',
                '-'
            ),

            "Tanggal":
            tanggal
        })

    # =========================
    # DATAFRAME
    # =========================
    df = pd.DataFrame(data)

    # =========================
    # SAVE TO MEMORY
    # =========================
    output = io.BytesIO()

    with pd.ExcelWriter(
        output,
        engine='openpyxl'
    ) as writer:

        df.to_excel(

            writer,

            index=False,

            sheet_name='Transactions'
        )

    output.seek(0)

    # =========================
    # DOWNLOAD
    # =========================
    return send_file(

        output,

        download_name='transactions.xlsx',

        as_attachment=True,

        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# =========================
# VOUCHER READY
# =========================
@admin.route('/admin/voucher-ready')
def voucher_ready():

    if not admin_required():
        return redirect('/admin/login')

    # =========================
    # SEARCH
    # =========================
    search = request.args.get(
        'search',
        ''
    )

    query = {

        "used": False
    }

    # =========================
    # SEARCH USERNAME
    # =========================
    if search:

        query["username"] = {

            "$regex": search,

            "$options": "i"
        }

    # =========================
    # GET DATA
    # =========================
    vouchers = list(

        vouchers_collection.find(query)
    )

    # =========================
    # PACKAGE
    # =========================
    for voucher in vouchers:

        package = packages_collection.find_one({

            "_id": ObjectId(
                voucher['package_id']
            )
        })

        voucher['package'] = package

    return render_template(

        'voucher_ready.html',

        vouchers=vouchers,

        search=search
    )

# =========================
# VOUCHER SOLD
# =========================
@admin.route('/admin/voucher-sold')
def voucher_sold():

    if not admin_required():
        return redirect('/admin/login')

    # =========================
    # SEARCH
    # =========================
    search = request.args.get(
        'search',
        ''
    )

    query = {

        "used": True
    }

    # =========================
    # SEARCH USERNAME
    # =========================
    if search:

        query["username"] = {

            "$regex": search,

            "$options": "i"
        }

    # =========================
    # GET DATA
    # =========================
    vouchers = list(

        vouchers_collection.find(query)
    )

    # =========================
    # PACKAGE & OWNER
    # =========================
    for voucher in vouchers:

        # PACKAGE
        package = packages_collection.find_one({

            "_id": ObjectId(
                voucher['package_id']
            )
        })

        voucher['package'] = package

        # OWNER
        if voucher.get('owner_id'):

            owner = users_collection.find_one({

                "_id": ObjectId(
                    voucher['owner_id']
                )
            })

            voucher['owner'] = owner

    return render_template(

        'voucher_sold.html',

        vouchers=vouchers,

        search=search
    )

# =========================
# ADD LOCATION
# =========================
@admin.route('/admin/add-location', methods=['GET', 'POST'])
def add_location():

    if not admin_required():
        return redirect('/admin/login')

    success_message = None
    error_message = None

    delete_message = request.args.get('delete')

    edit_message = request.args.get('edit')

    if request.method == 'POST':

        location_name = request.form['location_name']

        # cek lokasi sudah ada atau belum
        existing_location = locations_collection.find_one({

            "name": {

                "$regex": f"^{location_name}$",

                "$options": "i"
            }
        })

        if existing_location:

            error_message = "Lokasi sudah ada"

        else:

            locations_collection.insert_one({

                "name": location_name,

                "active": True
            })

            success_message = "Lokasi berhasil ditambahkan"

    locations = list(
        locations_collection.find()
    )

    return render_template(

        'add_location.html',

        locations=locations,

        success_message=success_message,

        error_message=error_message,

        delete_message=delete_message,

        edit_message=edit_message
    )

# =========================
# EDIT LOCATION
# =========================
@admin.route('/admin/edit-location/<location_id>', methods=['GET', 'POST'])
def edit_location(location_id):

    if not admin_required():
        return redirect('/admin/login')

    location = locations_collection.find_one({

        "_id": ObjectId(location_id)
    })

    if request.method == 'POST':

        new_name = request.form['location_name']

        locations_collection.update_one(

            {"_id": ObjectId(location_id)},

            {
                "$set": {

                    "name": new_name
                }
            }
        )

        return redirect('/admin/add-location?edit=Lokasi berhasil diupdate')

    return render_template(

        'edit_location.html',

        location=location
    )

# =========================
# DELETE LOCATION
# =========================
@admin.route('/admin/delete-location/<location_id>')
def delete_location(location_id):

    if not admin_required():
        return redirect('/admin/login')

    locations_collection.delete_one({

        "_id": ObjectId(location_id)
    })

    return redirect('/admin/add-location?delete=Lokasi berhasil dihapus')

# =========================
# ADD PACKAGE
# =========================
@admin.route('/admin/add-package', methods=['GET', 'POST'])
def add_package():

    if not admin_required():
        return redirect('/admin/login')

    success_message = None
    error_message = None

    delete_message = request.args.get('delete')

    edit_message = request.args.get('edit')

    locations = list(
        locations_collection.find()
    )

    if request.method == 'POST':

        location_id = request.form['location_id']

        package_name = request.form['package_name']

        duration = request.form['duration']

        price = request.form['price']

        # cek package duplicate
        existing_package = packages_collection.find_one({

            "location_id": location_id,

            "name": {

                "$regex": f"^{package_name}$",

                "$options": "i"
            },

            "duration": duration
        })

        if existing_package:

            error_message = "Package sudah ada"

        else:

            packages_collection.insert_one({

                "location_id": location_id,

                "name": package_name,

                "duration": duration,

                "price": int(price),

                "active": True
            })

            success_message = "Package berhasil ditambahkan"

    # =========================
    # PAGINATION
    # =========================

    page = request.args.get('page', 1, type=int)

    per_page = 10

    skip = (page - 1) * per_page

    # =========================
    # SEARCH
    # =========================

    search = request.args.get('search', '')

    query = {}

    if search:

        query["name"] = {

            "$regex": search,

            "$options": "i"
        }

    # =========================
    # TOTAL PACKAGE
    # =========================

    total_packages = packages_collection.count_documents(query)

    total_pages = (

        total_packages + per_page - 1

    ) // per_page

    # =========================
    # GET PACKAGE
    # =========================

    packages = list(

        packages_collection.find(query)

        .skip(skip)

        .limit(per_page)
    )

    return render_template(

    'add_package.html',

    locations=locations,

    packages=packages,

    success_message=success_message,

    error_message=error_message,

    delete_message=delete_message,

    edit_message=edit_message,

    page=page,

    total_pages=total_pages,

    search=search
)

# =========================
# DELETE PACKAGE
# =========================
@admin.route('/admin/delete-package/<package_id>')
def delete_package(package_id):

    if not admin_required():
        return redirect('/admin/login')

    packages_collection.delete_one({

        "_id": ObjectId(package_id)
    })

    return redirect('/admin/add-package?delete=Package berhasil dihapus')

# =========================
# ADD VOUCHER
# =========================
@admin.route('/admin/add-voucher', methods=['GET', 'POST'])
def add_voucher():

    if not admin_required():
        return redirect('/admin/login')

    success_message = None
    error_message = None

    delete_message = request.args.get('delete')

    edit_message = request.args.get('edit')

    locations = list(
        locations_collection.find()
    )

    packages = list(
        packages_collection.find()
    )

    if request.method == 'POST':

        location_id = request.form['location_id']

        package_id = request.form['package_id']

        username = request.form['username']

        password = request.form['password']

        # cek voucher duplicate
        existing_voucher = vouchers_collection.find_one({

            "username": {

                "$regex": f"^{username}$",

                "$options": "i"
            }
        })

        if existing_voucher:

            error_message = "Username voucher sudah ada"

        else:

            vouchers_collection.insert_one({

                "location_id": location_id,

                "package_id": package_id,

                "username": username,

                "password": password,

                "used": False,

                "owner_id": None,

                "transaction_id": None
            })

            success_message = "Voucher berhasil ditambahkan"

    # =========================
    # PAGINATION
    # =========================

    page = request.args.get('page', 1, type=int)

    per_page = 10

    skip = (page - 1) * per_page

    # =========================
    # SEARCH
    # =========================

    search = request.args.get('search', '')

    query = {

        "used": False
    }

    if search:

        query["username"] = {

            "$regex": search,

            "$options": "i"
        }

    # =========================
    # TOTAL DATA
    # =========================

    total_vouchers = vouchers_collection.count_documents(query)

    total_pages = (

        total_vouchers + per_page - 1

    ) // per_page

    # =========================
    # GET DATA
    # =========================

    vouchers = list(

        vouchers_collection.find(query)

        .skip(skip)

        .limit(per_page)
    )

    return render_template(

    'add_voucher.html',

    locations=locations,

    packages=packages,

    vouchers=vouchers,

    success_message=success_message,

    error_message=error_message,

    delete_message=delete_message,

    edit_message=edit_message,

    page=page,

    total_pages=total_pages,

    search=search
)

# =========================
# DELETE VOUCHER
# =========================
@admin.route('/admin/delete-voucher/<voucher_id>')
def delete_voucher(voucher_id):

    if not admin_required():
        return redirect('/admin/login')

    vouchers_collection.delete_one({

        "_id": ObjectId(voucher_id)
    })

    return redirect('/admin/add-voucher?delete=Voucher berhasil dihapus')

# =========================
# EDIT PACKAGE
# =========================
@admin.route('/admin/edit-package/<package_id>', methods=['GET', 'POST'])
def edit_package(package_id):

    if not admin_required():
        return redirect('/admin/login')

    package = packages_collection.find_one({

        "_id": ObjectId(package_id)
    })

    locations = list(
        locations_collection.find()
    )

    if request.method == 'POST':

        location_id = request.form['location_id']

        package_name = request.form['package_name']

        duration = request.form['duration']

        price = request.form['price']

        packages_collection.update_one(

            {"_id": ObjectId(package_id)},

            {
                "$set": {

                    "location_id": location_id,

                    "name": package_name,

                    "duration": duration,

                    "price": int(price)
                }
            }
        )

        return redirect('/admin/add-package?edit=Package berhasil diupdate')

    return render_template(

        'edit_package.html',

        package=package,

        locations=locations
    )

# =========================
# EDIT VOUCHER
# =========================
@admin.route('/admin/edit-voucher/<voucher_id>', methods=['GET', 'POST'])
def edit_voucher(voucher_id):

    if not admin_required():
        return redirect('/admin/login')

    voucher = vouchers_collection.find_one({

        "_id": ObjectId(voucher_id)
    })

    locations = list(
        locations_collection.find()
    )

    packages = list(
        packages_collection.find()
    )

    if request.method == 'POST':

        location_id = request.form['location_id']

        package_id = request.form['package_id']

        username = request.form['username']

        password = request.form['password']

        vouchers_collection.update_one(

            {"_id": ObjectId(voucher_id)},

            {
                "$set": {

                    "location_id": location_id,

                    "package_id": package_id,

                    "username": username,

                    "password": password
                }
            }
        )

        return redirect('/admin/add-voucher?edit=Voucher berhasil diupdate')

    return render_template(

        'edit_voucher.html',

        voucher=voucher,

        locations=locations,

        packages=packages
    )

