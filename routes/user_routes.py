from flask import (
    Blueprint,
    render_template,
    session,
    redirect,
    request,
    jsonify
)

from bson.objectid import ObjectId

from datetime import (
    datetime,
    timedelta
)



from utils.midtrans import snap

import os
import uuid


from database import (
    locations_collection,
    packages_collection,
    vouchers_collection,
    transactions_collection
)

user = Blueprint('user', __name__)

# =========================
# HOME
# =========================
@user.route('/')
def home():

    user_name = session.get('user_name')

    locations = list(
        locations_collection.find()
    )

    return render_template(
        'index.html',
        user_name=user_name,
        locations=locations
    )


# =========================
# DETAIL LOKASI
# =========================
@user.route('/location/<location_id>')
def location_detail(location_id):

    location = locations_collection.find_one({
        "_id": ObjectId(location_id)
    })

    packages = list(
        packages_collection.find({
            "location_id": location_id
        })
    )

    # hitung stok voucher
    for package in packages:

        stock = vouchers_collection.count_documents({

            "package_id": str(package['_id']),

            "used": False
        })

        package['stock'] = stock

    return render_template(
        'location_detail.html',
        location=location,
        packages=packages
    )


# =========================
# BELI VOUCHER
# =========================
@user.route('/buy/<package_id>')
def buy_voucher(package_id):

    # wajib login
    if 'user_id' not in session:
        return redirect('/login')

    # cek voucher tersedia
    available_voucher = vouchers_collection.find_one({

        "package_id": package_id,

        "used": False
    })

    if not available_voucher:
        return "Voucher habis"

    # ambil package
    package = packages_collection.find_one({

        "_id": ObjectId(package_id)
    })

    # buat transaksi
    transaction_id = f"ORDER-{uuid.uuid4()}"

    transaction = {

        "order_id": transaction_id,

        "user_id": session['user_id'],

        "package_id": package_id,

        "amount": package['price'],

        "payment_status": "UNPAID",

        "created_at": datetime.utcnow() + timedelta(hours=8)
    }

    result = transactions_collection.insert_one(
        transaction
    )

    transaction_id = f"ORDER-{uuid.uuid4()}"

    # =========================
    # MIDTRANS
    # =========================

    transaction_data = {

        "transaction_details": {

            "order_id": transaction_id,

            "gross_amount": package['price']
        },

        "customer_details": {

            "first_name": session['user_name']
        }
    }

    # generate snap token
    snap_token = snap.create_transaction_token(
        transaction_data
    )

    return render_template(

        'payment.html',

        package=package,

        transaction_id=transaction_id,

        snap_token=snap_token,

        client_key=os.getenv(
            "MIDTRANS_CLIENT_KEY"
        )
    )


# =========================
# DASHBOARD USER
# =========================
@user.route('/dashboard')
def dashboard():

    if 'user_id' not in session:
        return redirect('/login')

    # ambil transaksi terakhir yang PAID
    transaction = transactions_collection.find_one(

        {
            "user_id": session['user_id'],

            "payment_status": "PAID"
        },

        sort=[("purchase_time", -1)]
    )

    active_voucher = None

    if transaction:

        purchase_time = transaction.get(
            'purchase_time'
        )

        if purchase_time:

            voucher = vouchers_collection.find_one({

                "_id": ObjectId(
                    transaction['voucher_id']
                )
            })

            package = packages_collection.find_one({

                "_id": ObjectId(
                    transaction['package_id']
                )
            })

            # =========================
            # JIKA PACKAGE TIDAK DITEMUKAN
            # =========================

            if not package:

                active_voucher = {

                    "username": voucher['username'],

                    "password": voucher['password'],

                    "remaining_time": "Package sudah dihapus"
                }

                return render_template(

                    'dashboard.html',

                    user_name=session['user_name'],

                    active_voucher=active_voucher
                )

            # =========================
            # AMBIL DURASI
            # =========================

            duration_text = package['duration']

            duration_value = int(
                duration_text.split()[0]
            )

            # cek satuan
            if 'menit' in duration_text.lower():

                expire_time = purchase_time + timedelta(
                    minutes=duration_value
                )

            elif 'jam' in duration_text.lower():

                expire_time = purchase_time + timedelta(
                    hours=duration_value
                )

            else:

                # default jam
                expire_time = purchase_time + timedelta(
                    hours=duration_value
                )

            # voucher masih aktif
            if datetime.utcnow() + timedelta(hours=8) < expire_time:

                remaining_time = expire_time - (
                    datetime.utcnow() + timedelta(hours=8)
                )

                remaining_hours = (
                    remaining_time.seconds // 3600
                )

                remaining_minutes = (
                    (remaining_time.seconds % 3600) // 60
                )

                active_voucher = {

                    "username": voucher['username'],

                    "password": voucher['password'],

                    "remaining_time":

                    f"{remaining_hours} jam "
                    f"{remaining_minutes} menit"
                }

    return render_template(

        'dashboard.html',

        user_name=session['user_name'],

        active_voucher=active_voucher
    )


# =========================
# MIDTRANS CALLBACK
# =========================
@user.route(
    '/midtrans-callback',
    methods=['POST']
)
def midtrans_callback():

    print("\n========================")
    print("CALLBACK MASUK")
    print("========================\n")

    data = request.json

    print(data)

    order_id = data.get('order_id')

    transaction_status = data.get(
        'transaction_status'
    )

    fraud_status = data.get(
        'fraud_status'
    )

    print("ORDER ID:", order_id)
    print("STATUS:", transaction_status)

    # =========================
    # PAYMENT SUCCESS
    # =========================

    if (
        transaction_status == 'settlement'
        or
        (
            transaction_status == 'capture'
            and fraud_status == 'accept'
        )
    ):

        transaction = transactions_collection.find_one({

    "order_id": order_id
})

        if not transaction:

            print("TRANSACTION NOT FOUND")

            return jsonify({

                "message": "transaction not found"
            })

        # cegah double callback
        if transaction.get(
            'payment_status'
        ) == 'PAID':

            print("SUDAH PERNAH PAID")

            return jsonify({

                "message": "already paid"
            })

        # cari voucher tersedia
        voucher = vouchers_collection.find_one({

            "package_id": transaction['package_id'],

            "used": False
        })

        if not voucher:

            print("VOUCHER HABIS")

            return jsonify({

                "message": "voucher habis"
            })

        # update voucher
        vouchers_collection.update_one(

            {"_id": voucher['_id']},

            {
                "$set": {

                    "used": True,

                    "owner_id": transaction['user_id'],

                    "transaction_id": order_id
                }
            }
        )

        # update transaksi
        transactions_collection.update_one(

    {"order_id": order_id},

            {
                "$set": {

                    "payment_status": "PAID",

                    "voucher_id": str(voucher['_id']),

                    "purchase_time": datetime.utcnow() + timedelta(hours=8)
                }
            }
        )

        print("\n========================")
        print("PEMBAYARAN BERHASIL")
        print("========================\n")

    else:

        print("\n========================")
        print("PEMBAYARAN BELUM SUCCESS")
        print("========================\n")

    return jsonify({

        "message": "callback received"
    })

