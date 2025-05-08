from dotenv import load_dotenv
import os
import math
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
import random, zipfile, shutil, datetime, ffmpeg

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
    id                       = db.Column(db.Integer, primary_key=True)
    email                    = db.Column(db.String(150), unique=True, nullable=False)
    password                 = db.Column(db.String(150), nullable=False)
    username                 = db.Column(db.String(150), default='New User')
    backup_enabled           = db.Column(db.Boolean, default=False)
    dark_mode_enabled        = db.Column(db.Boolean, default=False)
    stripe_customer_id       = db.Column(db.String(100), nullable=True)
    stripe_subscription_id   = db.Column(db.String(100), nullable=True)
    plan                     = db.Column(db.String(50), default='free')
    tokens                   = db.Column(db.Integer, default=0)
    referral_code            = db.Column(db.String(20), unique=True, nullable=True)
    referred_by_id           = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    referrals                = db.relationship(
        'User', backref=db.backref('referrer', remote_side=[id]), lazy='dynamic'
    )

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ... (Auth, Settings, Plans, History, Downloads, Google Drive backup,
#      Helpers, Image processing routes unchanged) ...

# -------------------- Process Videos (rotation commented out) ----------
@app.route('/process-videos', methods=['POST'])
@login_required
def process_videos():
    vids      = request.files.getlist('videos')
    batch     = int(request.form.get('batch_size', 5))
    intensity = int(request.form.get('intensity', 30))
    opts = {
        'contrast':   'adjust_contrast'   in request.form,
        'brightness': 'adjust_brightness' in request.form,
        'rotate':     'rotate'            in request.form,  # rotation code commented below
        'crop':       'crop'              in request.form,
        'flip':       'flip_horizontal'   in request.form
    }

    ts            = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    output_folder = os.path.join('processed', ts)
    os.makedirs(output_folder, exist_ok=True)

    for vf in vids:
        src = os.path.join('uploads', vf.filename)
        vf.save(src)

        # probe to detect streams
        probe     = ffmpeg.probe(src)
        streams   = probe['streams']
        v_stream  = next(s for s in streams if s['codec_type'] == 'video')
        has_audio = any(s['codec_type'] == 'audio' for s in streams)
        w, h      = int(v_stream['width']), int(v_stream['height'])
        base      = os.path.splitext(vf.filename)[0]

        video_in = ffmpeg.input(src).video
        audio_in = ffmpeg.input(src).audio if has_audio else None

        for i in range(batch):
            outp = os.path.join(output_folder, f"{base}_variant_{i+1}.mp4")
            hist = os.path.join('static/history',   f"{base}_variant_{i+1}.mp4")
            v = video_in

            # contrast & brightness
            if opts['contrast'] or opts['brightness']:
                c = 1 + scale_range(-0.1, 0.1, intensity) if opts['contrast'] else 1
                b =     scale_range(-0.05, 0.05, intensity) if opts['brightness'] else 0
                v = v.filter('eq', contrast=c, brightness=b)

            # --- ROTATION (temporarily disabled) ---
            # if opts['rotate']:
            #     angle = scale_range(-2, 2, intensity) * math.pi/180
            #     v = v.filter(
            #         'rotate',
            #         angle,
            #         out_w='iw',
            #         out_h='ih',
            #     )

            # crop & scale back up
            if opts['crop']:
                dx = int(w * scale_range(0.01, 0.03, intensity))
                dy = int(h * scale_range(0.01, 0.03, intensity))
                v = v.filter('crop', w-2*dx, h-2*dy, dx, dy).filter('scale', w, h)

            # horizontal flip
            if opts['flip'] and random.random() > 0.5:
                v = v.filter('hflip')

            # mux video+audio only if audio exists
            if has_audio:
                stream = ffmpeg.output(v, audio_in, outp, vcodec='libx264', acodec='copy')
            else:
                stream = ffmpeg.output(v, outp, vcodec='libx264')

            try:
                ffmpeg.run(stream, overwrite_output=True, capture_stderr=True)
            except ffmpeg.Error as e:
                err = e.stderr.decode('utf-8', errors='ignore')
                current_app.logger.error(f"FFmpeg failed: {err}")
                return jsonify({
                    'error':  'Video processing failed',
                    'detail': err.strip().split('\n')[-1]
                }), 500

            shutil.copy(outp, hist)

        os.remove(src)

    # zip + cleanup
    zip_fn   = f"videos_{ts}.zip"
    zip_path = os.path.join('static/processed_zips', zip_fn)
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for f in os.listdir(output_folder):
            zf.write(os.path.join(output_folder, f), arcname=f)
    shutil.rmtree(output_folder)

    if current_user.backup_enabled:
        upload_to_google_drive(zip_path, zip_fn)

    return jsonify({'zip_filename': zip_fn})

# -------------------- OAuth Routes & Blueprints --------------------
@app.route('/oauth2start')
@login_required
def oauth2start():
    return start_auth()

@app.route('/oauth2callback')
def oauth2callback():
    return handle_callback()

app.register_blueprint(subscription_bp, url_prefix='/subscription')
app.register_blueprint(referral_bp,     url_prefix='/referral')

if __name__ == '__main__':
    app.run(debug=True)
