from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, send_from_directory, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, UserMixin, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
import random, zipfile, shutil, datetime

# Import billing blueprints
from billing import subscription_bp, referral_bp
# Import Google OAuth helpers
from google_drive import start_auth, handle_callback

# Import new processing logic
from image_videoprocessing import process_images_logic, process_videos_logic

# -------------------- Favicon --------------------
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

# -------------------- Folders --------------------
OUTPUT_FOLDER = "output"
HISTORY_FOLDER = "history"
UPLOADS_FOLDER = "uploads"
PROCESSED_ZIPS_FOLDER = "processed_zips"

for folder in (OUTPUT_FOLDER, HISTORY_FOLDER, UPLOADS_FOLDER, PROCESSED_ZIPS_FOLDER):
    os.makedirs(folder, exist_ok=True)

# -------------------- App & DB Setup --------------------
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'please_change_me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# -------------------- Login Manager --------------------
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# ... [User model, login loader, auth routes, etc. remain unchanged] ...

# -------------------- History & Downloads --------------
@app.route('/history')
@login_required
def history():
    page = int(request.args.get('page', 1))
    per_page = 25
    files = sorted(
        os.listdir(HISTORY_FOLDER),
        key=lambda x: os.path.getmtime(os.path.join(HISTORY_FOLDER, x)),
        reverse=True
    )
    total = (len(files) + per_page - 1) // per_page
    return render_template('history.html', files=files[(page-1)*per_page:page*per_page], page=page, total_pages=total)

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    return send_from_directory(HISTORY_FOLDER, filename, as_attachment=True)

@app.route('/download-zip/<filename>')
@login_required
def download_zip(filename):
    return send_from_directory(PROCESSED_ZIPS_FOLDER, filename, as_attachment=True)

# -------------------- Image/Video Processing ----------
@app.route('/process-images', methods=['POST'])
@login_required
def process_images():
    images = request.files.getlist('images')
    batch = int(request.form.get('batch_size', 5))
    intensity = int(request.form.get('intensity', 30))
    opts = {
        'contrast': 'adjust_contrast' in request.form,
        'brightness': 'adjust_brightness' in request.form,
        'rotate': 'rotate' in request.form,
        'crop': 'crop' in request.form,
        'flip': 'flip_horizontal' in request.form
    }
    # All variants go into flat output/history folders
    process_images_logic(images, batch, intensity, opts, OUTPUT_FOLDER, HISTORY_FOLDER)
    # Zip the files for user download
    ts = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    zip_fn = f"images_{ts}.zip"
    zp = os.path.join(PROCESSED_ZIPS_FOLDER, zip_fn)
    with zipfile.ZipFile(zp, 'w') as zf:
        for f in os.listdir(OUTPUT_FOLDER):
            zf.write(os.path.join(OUTPUT_FOLDER, f), arcname=f)
    # Optionally clean up output folder (remove processed files)
    for f in os.listdir(OUTPUT_FOLDER):
        os.remove(os.path.join(OUTPUT_FOLDER, f))
    if current_user.backup_enabled:
        upload_to_google_drive(zp, zip_fn)
    return jsonify({'zip_filename': zip_fn})

@app.route('/process-videos', methods=['POST'])
@login_required
def process_videos():
    vids = request.files.getlist('videos')
    batch = int(request.form.get('batch_size', 5))
    intensity = int(request.form.get('intensity', 30))
    opts = {
        'contrast': 'adjust_contrast' in request.form,
        'brightness': 'adjust_brightness' in request.form,
        'rotate': 'rotate' in request.form,
        'crop': 'crop' in request.form,
        'flip': 'flip_horizontal' in request.form
    }
    process_videos_logic(vids, batch, intensity, opts, OUTPUT_FOLDER, HISTORY_FOLDER)
    ts = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    zip_fn = f"videos_{ts}.zip"
    zp = os.path.join(PROCESSED_ZIPS_FOLDER, zip_fn)
    with zipfile.ZipFile(zp, 'w') as zf:
        for f in os.listdir(OUTPUT_FOLDER):
            zf.write(os.path.join(OUTPUT_FOLDER, f), arcname=f)
    for f in os.listdir(OUTPUT_FOLDER):
        os.remove(os.path.join(OUTPUT_FOLDER, f))
    if current_user.backup_enabled:
        upload_to_google_drive(zp, zip_fn)
    return jsonify({'zip_filename': zip_fn})

# ... [The rest of your routes and main block remain unchanged] ...
if __name__ == '__main__':
    app.run(debug=True)
