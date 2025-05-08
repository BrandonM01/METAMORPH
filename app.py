# app.py
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
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(150), default='New User')
    backup_enabled = db.Column(db.Boolean, default=False)
    dark_mode_enabled = db.Column(db.Boolean, default=False)
    stripe_customer_id     = db.Column(db.String(100), nullable=True)
    stripe_subscription_id = db.Column(db.String(100), nullable=True)
    plan                   = db.Column(db.String(50), default='free')
    tokens                 = db.Column(db.Integer, default=0)
    referral_code          = db.Column(db.String(20), unique=True, nullable=True)
    referred_by_id         = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    referrals              = db.relationship(
        'User', backref=db.backref('referrer', remote_side=[id]), lazy='dynamic'
    )

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# -------------------- Auth & Referral --------------------
@app.route('/apply-referral/<code>')
def apply_referral(code):
    session['referral_code'] = code
    return redirect(url_for('register'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        pwd   = request.form['password']
        if User.query.filter_by(email=email).first():
            flash('⚠️ Email already registered.', 'error')
            return redirect(url_for('register'))
        new_user = User(
            email=email,
            password=generate_password_hash(pwd),
            username=email.split('@')[0]
        )
        code = session.pop('referral_code', None)
        if code:
            ref = User.query.filter_by(referral_code=code).first()
            if ref and ref.id != new_user.id:
                new_user.referred_by_id = ref.id
                ref.tokens += 10
                db.session.add(ref)
        new_user.referral_code = ''.join(
            random.choices(random.choices.__defaults__[0] + random.choices.__defaults__[1], k=8)
        )
        db.session.add(new_user)
        db.session.commit()
        flash('✅ Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        pwd   = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, pwd):
            login_user(user)
            return redirect(url_for('home'))
        flash('❌ Login failed. Check your credentials.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('👋 Logged out successfully.', 'success')
    return redirect(url_for('login'))

# -------------------- Settings --------------------
@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        current_user.username         = request.form.get('username', current_user.username)
        current_user.backup_enabled   = 'backup_enabled' in request.form
        current_user.dark_mode_enabled= 'dark_mode_enabled' in request.form
        db.session.commit()
        flash('✅ Settings updated.', 'success')
        return redirect(url_for('settings'))
    link = url_for('apply_referral', code=current_user.referral_code, _external=True)
    return render_template('settings.html', referral_link=link)

# -------------------- Plans & Stripe Key --------------------
@app.route('/plans')
@login_required
def plans():
    return render_template('plans.html',
        stripe_publishable_key=os.getenv('STRIPE_PUBLISHABLE_KEY')
    )

@app.route('/stripe-key')
@login_required
def stripe_key():
    return jsonify({'publishableKey': os.getenv('STRIPE_PUBLISHABLE_KEY')})

# -------------------- UI Pages --------------------
@app.route('/')
@login_required
def home():            return render_template('home.html')
@app.route('/image-processor')
@login_required
def image_processor():return render_template('image_processor.html')
@app.route('/video-processor')
@login_required
def video_processor():return render_template('video_processor.html')

# -------------------- History & Downloads --------------------
@app.route('/history')
@login_required
def history():
    page = int(request.args.get('page',1))
    per_page = 25
    folder = 'static/history'
    files  = sorted(
        os.listdir(folder),
        key=lambda f: os.path.getmtime(os.path.join(folder, f)),
        reverse=True
    )
    chunk = files[(page-1)*per_page:page*per_page]
    total = (len(files)+per_page-1)//per_page
    return render_template('history.html', files=chunk, page=page, total_pages=total)

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    return send_from_directory('static/history', filename, as_attachment=True)

@app.route('/download-zip/<filename>')
@login_required
def download_zip(filename):
    return send_from_directory('static/processed_zips', filename, as_attachment=True)

# -------------------- Google Drive Backup --------------------
def upload_to_google_drive(file_path, filename):
    gauth = GoogleAuth()
    gauth.LoadCredentialsFile("credentials.json")
    if     gauth.credentials is None: gauth.LocalWebserverAuth()
    elif   gauth.access_token_expired: gauth.Refresh()
    else:   gauth.Authorize()
    gauth.SaveCredentialsFile("credentials.json")

    drive = GoogleDrive(gauth)
    fl = drive.ListFile({
      'q': "title='MetadataChangerBackup' "
           "and mimeType='application/vnd.google-apps.folder' "
           "and trashed=false"
    }).GetList()

    if fl:
        fid = fl[0]['id']
    else:
        folder = drive.CreateFile({
          'title':'MetadataChangerBackup',
          'mimeType':'application/vnd.google-apps.folder'
        })
        folder.Upload()
        fid = folder['id']

    f = drive.CreateFile({'title':filename,'parents':[{'id':fid}]})
    f.SetContentFile(file_path)
    f.Upload()

# -------------------- Helpers ----------
def scale_range(min_val, max_val, intensity):
    factor = intensity / 100
    return random.uniform(min_val*factor, max_val*factor)

# -------------------- Process Images ----------
@app.route('/process-images', methods=['POST'])
@login_required
def process_images():
    images    = request.files.getlist('images')
    batch     = int(request.form.get('batch_size',5))
    intensity = int(request.form.get('intensity',30))
    opts = {
        'contrast':   'adjust_contrast'   in request.form,
        'brightness': 'adjust_brightness' in request.form,
        'rotate':     'rotate'           in request.form,
        'crop':       'crop'             in request.form,
        'flip':       'flip_horizontal'  in request.form
    }

    ts     = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    outdir = os.path.join('processed', ts)
    os.makedirs(outdir, exist_ok=True)

    for imgf in images:
        img = Image.open(imgf)
        base = os.path.splitext(imgf.filename)[0]
        for i in range(batch):
            var = img.copy()
            if opts['contrast']:   var = ImageEnhance.Contrast(var).enhance(1+scale_range(-0.1,0.1,intensity))
            if opts['brightness']: var = ImageEnhance.Brightness(var).enhance(1+scale_range(-0.1,0.1,intensity))
            if opts['rotate']:     var = var.rotate(scale_range(-5,5,intensity),expand=True)
            if opts['crop']:
                w,h = var.size
                dx,dy = int(w*scale_range(0.01,0.05,intensity)),int(h*scale_range(0.01,0.05,intensity))
                var = var.crop((dx,dy,w-dx,h-dy))
            if opts['flip'] and random.random()>0.5:
                var = var.transpose(Image.FLIP_LEFT_RIGHT)

            fn = f"{base}_variant_{i+1}.jpg"
            var.save(os.path.join(outdir, fn))
            var.save(os.path.join('static/history', fn))

    zip_fn  = f"images_{ts}.zip"
    zippath = os.path.join('static/processed_zips', zip_fn)
    with zipfile.ZipFile(zippath, 'w') as zf:
        for f in os.listdir(outdir):
            zf.write(os.path.join(outdir, f), arcname=f)

    shutil.rmtree(outdir)
    if current_user.backup_enabled:
        upload_to_google_drive(zippath, zip_fn)

    return jsonify({'zip_filename': zip_fn})


# -------------------- Process Videos ----------
@app.route('/process-videos', methods=['POST'])
@login_required
def process_videos():
    vids      = request.files.getlist('videos')
    batch     = int(request.form.get('batch_size', 5))
    intensity = int(request.form.get('intensity', 30))
    opts = {
        'contrast':   'adjust_contrast'   in request.form,
        'brightness': 'adjust_brightness' in request.form,
        'rotate':     'rotate'            in request.form,
        'crop':       'crop'              in request.form,
        'flip':       'flip_horizontal'   in request.form
    }

    ts            = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    output_folder = os.path.join('processed', ts)
    os.makedirs(output_folder, exist_ok=True)

    for vf in vids:
        src = os.path.join('uploads', vf.filename)
        vf.save(src)

        # probe to see if there's an audio stream
        info     = ffmpeg.probe(src)
        v_stream = next(s for s in info['streams'] if s['codec_type']=='video')
        has_audio = any(s['codec_type']=='audio' for s in info['streams'])
        w, h     = int(v_stream['width']), int(v_stream['height'])
        base     = os.path.splitext(vf.filename)[0]

        # separate inputs
        video_in = ffmpeg.input(src).video
        if has_audio:
            audio_in = ffmpeg.input(src).audio

        for i in range(batch):
            outp = os.path.join(output_folder, f"{base}_variant_{i+1}.mp4")
            hist = os.path.join('static/history',   f"{base}_variant_{i+1}.mp4")

            # apply filters to video only
            v = video_in
            if opts['contrast'] or opts['brightness']:
                c = 1 + scale_range(-0.1, 0.1, intensity) if opts['contrast'] else 1
                b =     scale_range(-0.05,0.05,intensity) if opts['brightness'] else 0
                v = v.filter('eq', contrast=c, brightness=b)

            if opts['rotate']:
                angle = scale_range(-2, 2, intensity) * math.pi/180
                v = v.filter(
                    'rotate',
                    angle,
                    out_w='iw',
                    out_h='ih'
                )

            if opts['crop']:
                dx, dy = (
                    int(w * scale_range(0.01,0.03,intensity)),
                    int(h * scale_range(0.01,0.03,intensity))
                )
                v = v.filter('crop', w-2*dx, h-2*dy, dx, dy).filter('scale', w, h)

            if opts['flip'] and random.random()>0.5:
                v = v.filter('hflip')

            # build the ffmpeg.output call differently if there's no audio
            if has_audio:
                stream = ffmpeg.output(
                    v, audio_in,
                    outp,
                    vcodec='libx264',
                    acodec='copy'
                )
            else:
                stream = ffmpeg.output(
                    v,
                    outp,
                    vcodec='libx264'
                )

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

    # zip up all variants
    zip_fn   = f"videos_{ts}.zip"
    zip_path = os.path.join('static/processed_zips', zip_fn)
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for f in os.listdir(output_folder):
            zf.write(os.path.join(output_folder, f), arcname=f)

    shutil.rmtree(output_folder)
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
