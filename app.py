from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, send_from_directory, jsonify, current_app
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
from PIL import Image, ImageEnhance
import random
import zipfile
import shutil
import datetime
import ffmpeg

# Import billing blueprints
from billing import subscription_bp, referral_bp
# Import Google OAuth helpers
from google_drive import start_auth, handle_callback

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

# -------------------- Ensure Folders --------------------
for folder in ('uploads', 'processed', 'static/history', 'static/processed_zips'):
    os.makedirs(folder, exist_ok=True)

# -------------------- Models --------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    # ... other fields unchanged ...

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# -------------------- Routes & Other handlers unchanged --------------------
# ... (register, login, logout, settings, plans, UI pages, history, downloads, Google Drive backup, image processing) ...

# -------------------- Process Videos (v7.1) ----------
@app.route('/process-videos', methods=['POST'])
@login_required
def process_videos():
    vids = request.files.getlist('videos')
    batch = int(request.form.get('batch_size', 5))
    intensity = int(request.form.get('intensity', 30))
    opts = {
        'contrast':   'adjust_contrast'   in request.form,
        'brightness': 'adjust_brightness' in request.form,
        'rotate':     'rotate'           in request.form,
        'crop':       'crop'             in request.form,
        'flip':       'flip_horizontal'  in request.form
    }
    ts = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    out_dir = os.path.join('processed', ts)
    os.makedirs(out_dir, exist_ok=True)

    for vf in vids:
        src = os.path.join('uploads', vf.filename)
        vf.save(src)
        probe = ffmpeg.probe(src)
        v_stream = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        w, h = int(v_stream['width']), int(v_stream['height'])
        base = os.path.splitext(vf.filename)[0]

        for i in range(batch):
            outp = os.path.join(out_dir, f"{base}_variant_{i+1}.mp4")
            hist = os.path.join('static/history', f"{base}_variant_{i+1}.mp4")
            st = ffmpeg.input(src)

            # apply filters
            if opts['contrast'] or opts['brightness']:
                c = 1 + scale_range(-0.1, 0.1, intensity) if opts['contrast'] else 1
                b = scale_range(-0.05, 0.05, intensity) if opts['brightness'] else 0
                st = st.filter('eq', contrast=c, brightness=b)
            if opts['rotate']:
                angle = scale_range(-2, 2, intensity) * 3.1415 / 180
                st = st.filter('rotate', angle)
            if opts['crop']:
                dx = int(w * scale_range(0.01, 0.03, intensity))
                dy = int(h * scale_range(0.01, 0.03, intensity))
                st = st.filter('crop', w - 2*dx, h - 2*dy, dx, dy).filter('scale', w, h)
            if opts['flip'] and random.random() > 0.5:
                st = st.filter('hflip')

            # encode video, copy audio, capture stderr
            stream = ffmpeg.output(st, outp, vcodec='libx264', acodec='copy')
            try:
                ffmpeg.run(stream, overwrite_output=True, capture_stderr=True)
            except ffmpeg.Error as e:
                err = e.stderr.decode('utf-8', errors='ignore')
                current_app.logger.error(f"FFmpeg failed: {err}")
                return jsonify({'error': 'Video processing failed', 'detail': err}), 500

            shutil.copy(outp, hist)

        os.remove(src)

    # zip all variants
    zip_fn = f"videos_{ts}.zip"
    zip_path = os.path.join('static/processed_zips', zip_fn)
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for f in os.listdir(out_dir):
            zf.write(os.path.join(out_dir, f), arcname=f)
    shutil.rmtree(out_dir)
    if current_user.backup_enabled:
        upload_to_google_drive(zip_path, zip_fn)

    return jsonify({'zip_filename': zip_fn})

# -------------------- OAuth Routes --------------------
@app.route('/oauth2start')
@login_required
def oauth2start():
    return start_auth()

@app.route('/oauth2callback')
def oauth2callback():
    return handle_callback()

# -------------------- Blueprints --------------------
app.register_blueprint(subscription_bp, url_prefix='/subscription')
app.register_blueprint(referral_bp,     url_prefix='/referral')

if __name__ == '__main__':
    app.run(debug=True)
