import os
import mysql.connector
# DB connection settings vendorinvoiceautomation db

db_config = {
    'host': os.getenv("VENDOR_DB_HOST"),
    'port':int(os.getenv("MARKETPLACE_DB_PORT", 3306)),
    'user': os.getenv("VENDOR_DB_USER"),
    'password': os.getenv("VENDOR_DB_PASS"),
    'database': os.getenv("VENDOR_DB_NAME"),
     
}
def get_db_connection():
    return mysql.connector.connect(**db_config)

marketplace_config = {
    "host": os.getenv("MARKETPLACE_DB_HOST"),
    "port": int(os.getenv("MARKETPLACE_DB_PORT", 3306)),
    "user": os.getenv("MARKETPLACE_DB_USER"),
    "password": os.getenv("MARKETPLACE_DB_PASS"),
    "database": os.getenv("MARKETPLACE_DB_NAME"),
    "connection_timeout": 5,
    "connect_timeout": 5,
}



