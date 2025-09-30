import os
import logging
from flask import Flask
from db import init_app as init_db, db

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")

# Initialize database
init_db(app)

# Import models so SQLAlchemy is aware of them before creating tables
from models import Meeting, Response  # noqa: F401

# Create tables on startup if they don't exist
with app.app_context():
    db.create_all()

# Import routes after app creation to avoid circular imports
from routes import *

if __name__ == '__main__':
    # Development server only. In production use Gunicorn.
    app.run(host='0.0.0.0', port=5000, debug=False)
