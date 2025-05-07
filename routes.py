from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image, ImageEnhance
import os, shutil, zipfile, ffmpeg, datetime
from app import db, User
from helpers import upload_to_google_drive, scale_range

routes_bp = Blueprint('routes', __name__)

@routes_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            flash('⚠️ Email already registered.', 'error')
            return redirect(url_for('routes.register'))
        new_user = User(email=email, password=generate_password_hash(password), username=email.split('@')[0])
        db.session.add(new_user)
        db.session.commit()
        flash('✅ Registration successful!', 'success')
        return redirect(url_for('routes.login'))
    return render_template('register.html')

@routes_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('routes.home'))
        flash('❌ Login failed.', 'error')
    return render_template('login.html')

@routes_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('👋 Logged out.', 'success')
    return redirect(url_for('routes.login'))

@routes_bp.route('/')
@login_required
def home():
    return render_template('home.html')

@routes_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        current_user.username = request.form.get('username')
        current_user.backup_enabled = 'backup_enabled' in request.form
        current_user.dark_mode_enabled = 'dark_mode_enabled' in request.form
        db.session.commit()
        flash('✅ Settings updated.', 'success')
        return redirect(url_for('routes.settings'))
    return render_template('settings.html')

@routes_bp.route('/image-processor')
@login_required
def image_processor():
    return render_template('image_processor.html')

@routes_bp.route('/video-processor')
@login_required
def video_processor():
    return render_template('video_processor.html')

@routes_bp.route('/history')
@login_required
def history():
    page = int(request.args.get('page', 1))
    per_page = 25
    folder = os.path.join('static', 'history')
    all_files = sorted(os.listdir(folder), key=lambda f: os.path.getmtime(os.path.join(folder, f)), reverse=True)
    files = all_files[(page - 1) * per_page: page * per_page]
    return render_template('history.html', files=files, page=page, total_pages=(len(all_files) + per_page - 1) // per_page)

@routes_bp.route('/download/<filename>')
@login_required
def download_file(filename):
    return send_from_directory('static/history', filename, as_attachment=True)

@routes_bp.route('/download-zip/<filename>')
@login_required
def download_zip(filename):
    return send_from_directory('static/processed_zips', filename, as_attachment=True)
