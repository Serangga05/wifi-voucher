from flask import Flask, render_template, request, abort
from dotenv import load_dotenv
import os

from routes.auth_routes import auth
from routes.user_routes import user
from routes.admin_routes import admin

# Load .env
load_dotenv()

app = Flask(__name__)

# Secret key
app.secret_key = os.getenv("SECRET_KEY")

# Register blueprint
app.register_blueprint(auth)
app.register_blueprint(user)
app.register_blueprint(admin)


# ==============================
# ROUTE SEMENTARA UNTUK LIVE
# ==============================
@app.route('/live-rangga')
def live_rangga():
    key = request.args.get('key')
    live_key = os.getenv("LIVE_PAGE_KEY")

    if key != live_key:
        abort(404)

    return render_template('live_rangga.html')


# Run app
if __name__ == '__main__':
    app.run(debug=True)