import midtransclient
import os
from dotenv import load_dotenv

load_dotenv()

SERVER_KEY = os.getenv(
    "MIDTRANS_SERVER_KEY"
)

CLIENT_KEY = os.getenv(
    "MIDTRANS_CLIENT_KEY"
)

snap = midtransclient.Snap(

    is_production=False,

    server_key=SERVER_KEY.strip(),

    client_key=CLIENT_KEY.strip()
)