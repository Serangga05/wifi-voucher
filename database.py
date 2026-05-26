from pymongo import MongoClient
from dotenv import load_dotenv
import os

# Load .env
load_dotenv()

# Config
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME")

# Connect MongoDB
client = MongoClient(MONGODB_URI)

# Database
db = client[DB_NAME]

# Collections
users_collection = db.users
locations_collection = db.locations
packages_collection = db.packages
vouchers_collection = db.vouchers
transactions_collection = db.transactions