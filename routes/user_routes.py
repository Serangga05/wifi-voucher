from flask import (
    Blueprint,
    render_template,
    session,
    redirect,
    request,
    jsonify
)

from bson.objectid import ObjectId
from pymongo import ReturnDocument

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

    for package in packages:

        stock = vouchers_collection.count_documents({

            "package_id": str(package['_id']),

            "used": False,

            "reserved": {
                "$ne": True
            }
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
print("VERSI RESERVE VOUCHER AKTIF")
@user.route('/buy/<package_id>')
def buy_voucher(package_id):

    if 'user_id' not in session:
        return redirect('/login')

    package = packages_collection.find_one({
        "_id": ObjectId(package_id)
    })

    if not package:
        return "Package tidak ditemukan"

    transaction_id = f"ORDER-{uuid.uuid4()}"

    now = datetime.utcnow() + timedelta(hours=8)

    # reserve voucher secara aman
    reserved_voucher = vouchers_collection.find_one_and_update(

        {
            "package_id": package_id,

            "used": False,

            "reserved": {
                "$ne": True
            }
        },

        {
            "$set": {

                "reserved": True,

                "reserved_by": session['user_id'],

                "reserved_order_id": transaction_id,

                "reserved_at": now
            }
        },

        return_document=ReturnDocument.AFTER
    )

    if not reserved_voucher:
        return "Voucher habis"

    transaction = {

        "order_id": transaction_id,

        "user_id": session['user_id'],

        "package_id": package_id,

        "voucher_id": str(reserved_voucher['_id']),

        "amount": package['price'],

        "payment_status": "UNPAID",

        "created_at": now
    }

    transactions_collection.insert_one(transaction)

    transaction_data = {

        "transaction_details": {

            "order_id": transaction_id,

            "gross_amount": package['price']
        },

        "customer_details": {

            "first_name": session['user_name']
        }
    }

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

    # ambil semua transaksi PAID
    transactions = list(

        transactions_collection.find({

            "user_id": session['user_id'],

            "payment_status": "PAID"
        })
    )

    active_vouchers = []

    for transaction in transactions:

        purchase_time = transaction.get(
            'purchase_time'
        )

        if not purchase_time:
            continue

        # ambil voucher
        voucher = vouchers_collection.find_one({

            "_id": ObjectId(
                transaction['voucher_id']
            )
        })

        if not voucher:
            continue

                # ambil expire time dari transaksi
        expire_time = transaction.get(
            'expire_time'
        )

        if not expire_time:
            continue

        now = datetime.utcnow() + timedelta(hours=8)

        # jika voucher sudah expired
        if now >= expire_time:

            vouchers_collection.update_one(

                {"_id": voucher['_id']},

                {
                    "$set": {
                        "is_expired": True
                    }
                }
            )

            transactions_collection.update_one(

                {"_id": transaction['_id']},

                {
                    "$set": {
                        "is_expired": True
                    }
                }
            )

            continue

        # cek masih aktif
        if now < expire_time:

            remaining_time = expire_time - now

            remaining_hours = (
                remaining_time.seconds // 3600
            )

            remaining_minutes = (
                (remaining_time.seconds % 3600) // 60
            )

            # ambil package
            package = packages_collection.find_one({
                "_id": ObjectId(transaction['package_id'])
            })

            location_name = "-"

            package_name = "-"

            if package:

                package_name = package['name']

                location = locations_collection.find_one({
                    "_id": ObjectId(package['location_id'])
                })

                if location:
                    location_name = location['name']

            active_vouchers.append({

                "location_name": location_name,

                "package_name": package_name,

                "username": voucher['username'],

                "password": voucher['password'],

                "remaining_time":

                f"{remaining_hours} jam "
                f"{remaining_minutes} menit"
            })

    return render_template(

        'dashboard.html',

        user_name=session['user_name'],

        active_vouchers=active_vouchers
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

    transaction = transactions_collection.find_one({
        "order_id": order_id
    })

    if not transaction:

        print("TRANSACTION NOT FOUND")

        return jsonify({
            "message": "transaction not found"
        })

    if transaction.get('payment_status') == 'PAID':

        print("SUDAH PERNAH PAID")

        return jsonify({
            "message": "already paid"
        })

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

        voucher = vouchers_collection.find_one({
            "_id": ObjectId(transaction['voucher_id'])
        })

        if not voucher:

            print("VOUCHER NOT FOUND")

            return jsonify({
                "message": "voucher not found"
            })

        package = packages_collection.find_one({
            "_id": ObjectId(transaction['package_id'])
        })

        purchase_time = datetime.utcnow() + timedelta(hours=8)

        duration_text = package['duration']

        duration_value = int(
            duration_text.split()[0]
        )

        if 'menit' in duration_text.lower():

            expire_time = purchase_time + timedelta(
                minutes=duration_value
            )

        elif 'jam' in duration_text.lower():

            expire_time = purchase_time + timedelta(
                hours=duration_value
            )

        else:

            expire_time = purchase_time + timedelta(
                hours=duration_value
            )

        vouchers_collection.update_one(

            {"_id": voucher['_id']},

            {
                "$set": {

                    "used": True,

                    "reserved": False,

                    "owner_id": transaction['user_id'],

                    "transaction_id": order_id,

                    "purchase_time": purchase_time,

                    "expire_time": expire_time,

                    "is_expired": False
                },

                "$unset": {

                    "reserved_by": "",

                    "reserved_order_id": "",

                    "reserved_at": ""
                }
            }
        )

        transactions_collection.update_one(

            {"order_id": order_id},

            {
                "$set": {

                    "payment_status": "PAID",

                    "purchase_time": purchase_time,

                    "expire_time": expire_time
                }
            }
        )

        print("\n========================")
        print("PEMBAYARAN BERHASIL")
        print("========================\n")

    # =========================
    # PAYMENT FAILED / EXPIRED
    # =========================
    elif transaction_status in ['cancel', 'deny', 'expire']:

        vouchers_collection.update_one(

            {"_id": ObjectId(transaction['voucher_id'])},

            {
                "$set": {

                    "reserved": False
                },

                "$unset": {

                    "reserved_by": "",

                    "reserved_order_id": "",

                    "reserved_at": ""
                }
            }
        )

        transactions_collection.update_one(

            {"order_id": order_id},

            {
                "$set": {

                    "payment_status": "FAILED"
                }
            }
        )

        print("PEMBAYARAN GAGAL / EXPIRED")

    else:

        transactions_collection.update_one(

            {"order_id": order_id},

            {
                "$set": {

                    "payment_status": "PENDING"
                }
            }
        )

        print("PEMBAYARAN PENDING")

    return jsonify({
        "message": "callback received"
    })