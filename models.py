from flask_login import UserMixin
from app import db
from datetime import datetime

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))
    username = db.Column(db.String(150), default='New User')

    plan = db.Column(db.String(50), default='free')  # 'free', 'pro', 'enterprise'
    token_balance = db.Column(db.Integer, default=100)
    last_token_refresh = db.Column(db.DateTime, default=datetime.utcnow)

    backup_enabled = db.Column(db.Boolean, default=False)
    dark_mode_enabled = db.Column(db.Boolean, default=False)

    referral_code = db.Column(db.String(20), unique=True, nullable=True)
    referred_by = db.Column(db.String(20), nullable=True)

    billing_anchor = db.Column(db.DateTime, nullable=True)

    drive_folder_id = db.Column(db.String(300), nullable=True)
