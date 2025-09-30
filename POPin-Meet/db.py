import os
from flask_sqlalchemy import SQLAlchemy

# Global SQLAlchemy instance

db = SQLAlchemy()

def init_app(app):
    # Database URI
    database_url = os.environ.get("DATABASE_URL", "sqlite:///app.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
