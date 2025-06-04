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
from PIL import Image, ImageEnhance
import random, zipfile, shutil, datetime, ffmpeg

# Import billing blueprints
from billing import subscription_bp, referral_bp
# Import Google OAuth helpers
from google_drive import start_auth, handle_callback

# Import token.py
from tokens import deduct_tokens, reset_user_tokens, get_plan_tokens

# ---- Import your image and video processing logic ----
from image_videoprocessing import process_images_logic, process_videos_logic

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

# -------------------- Folders --------------------
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
    referral_code   = db.Column(db.String(20), unique=True, nullable=True)
    referred_by_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    referrals       = db.relationship(
        'User', backref=db.backref('referrer', remote_side=[id]), lazy='dynamic'
    )
    billing_anchor = db.Column(db.DateTime, nullable=True)
    
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# -------------------- Auth & Referral --------------------
import string

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        try:
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
                random.choices(string.ascii_letters + string.digits, k=8)
            )
            db.session.add(new_user)
            db.session.commit()
            flash('✅ Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            print("Registration error:", e)
            flash('❌ Registration failed. Please try again or contact support.', 'error')
            return redirect(url_for('register'))
    return render_template('register.html')
    
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        pwd   = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, pwd):
            login_user(user)
            return redirect(url_for('home'))
        flash('❌ Login failed. Check your credentials.','error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('👋 Logged out successfully.','success')
    return redirect(url_for('login'))

@app.route('/apply-referral/<code>')
def apply_referral(code):
    session['referral_code'] = code
    return redirect(url_for('register'))

# -------------------- Settings --------------------
@app.route('/settings', methods=['GET','POST'])
@login_required
def settings():
    if request.method == 'POST':
        current_user.username = request.form.get('username', current_user.username)
        current_user.backup_enabled = 'backup_enabled' in request.form
        current_user.dark_mode_enabled = 'dark_mode_enabled' in request.form
        db.session.commit()
        flash('✅ Settings updated.','success')
        return redirect(url_for('settings'))
    referral_link = url_for('apply_referral', code=current_user.referral_code, _external=True)
    return render_template(
    'settings.html',
    referral_link=referral_link,
    referral_code=current_user.referral_code  # Pass the code to the template
)

# -------------------- Plans & Stripe Key -------------------
@app.route('/plans')
@login_required
def plans():
    key = os.getenv('STRIPE_PUBLISHABLE_KEY')
    return render_template('plans.html', stripe_publishable_key=key)

@app.route('/stripe-key')
@login_required
def stripe_key():
    return jsonify({'publishableKey': os.getenv('STRIPE_PUBLISHABLE_KEY')})

# -------------------- UI Pages --------------------
@app.route('/')
@login_required
def home(): return render_template('home.html')
@app.route('/image-processor')
@login_required
def image_processor(): return render_template('image_processor.html')
@app.route('/video-processor')
@login_required
def video_processor(): return render_template('video_processor.html')

# -------------------- History & Downloads --------------
@app.route('/history')
@login_required
def history():
    page = int(request.args.get('page',1))
    per_page=25
    hist_folder='static/history'
    files=sorted(
        os.listdir(hist_folder),
        key=lambda x: os.path.getmtime(os.path.join(hist_folder,x)),
        reverse=True
    )
    total=(len(files)+per_page-1)//per_page
    return render_template('history.html', files=files[(page-1)*per_page:page*per_page], page=page, total_pages=total)

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    return send_from_directory('static/history', filename, as_attachment=True)
@app.route('/download-zip/<filename>')
@login_required
def download_zip(filename):
    return send_from_directory('static/processed_zips', filename, as_attachment=True)

# -------------------- Google Drive Backup -------------
def upload_to_google_drive(file_path, filename):
    gauth = GoogleAuth()
    gauth.LoadCredentialsFile("credentials.json")
    if gauth.credentials is None:
        gauth.LocalWebserverAuth()
    elif gauth.access_token_expired:
        gauth.Refresh()
    else:
        gauth.Authorize()
    gauth.SaveCredentialsFile("credentials.json")

    drive=GoogleDrive(gauth)
    folder_list=drive.ListFile({'q': "title='MetadataChangerBackup' and mimeType='application/vnd.google-apps.folder' and trashed=false"}).GetList()
    if folder_list:
        folder_id=folder_list[0]['id']
    else:
        folder=drive.CreateFile({'title':'MetadataChangerBackup', 'mimeType':'application/vnd.google-apps.folder'})
        folder.Upload()
        folder_id=folder['id']
    f=drive.CreateFile({'title':filename,'parents':[{'id':folder_id}]})
    f.SetContentFile(file_path)
    f.Upload()

# -------------------- Image/Video Processing ----------
def scale_range(min_val,max_val,intensity): 
    return random.uniform(min_val*(intensity/100), max_val*(intensity/100))

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
    ts = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    out = os.path.join('processed', ts)
    os.makedirs(out, exist_ok=True)

    # --- TOKEN CHECK ---
    tokens_needed = len(images) * batch * 1  # 1 token per image variant
    if current_user.tokens < tokens_needed:
        return jsonify({'error': "Not enough tokens", 'tokens_left': current_user.tokens}), 402

    # --- MAIN PROCESSING ---
    process_images_logic(
        images, batch, intensity, opts,
        out=out,
        hist_folder='static/history'
    )

    # --- DEDUCT TOKENS ---
    deduct_tokens(current_user, tokens_needed, db)

    zip_fn = f"images_{ts}.zip"
    zp = os.path.join('static/processed_zips', zip_fn)
    with zipfile.ZipFile(zp, 'w') as zf:
        for f in os.listdir(out):
            zf.write(os.path.join(out, f), arcname=f)
    shutil.rmtree(out)
    if current_user.backup_enabled:
        upload_to_google_drive(zp, zip_fn)
    return jsonify({'zip_filename': zip_fn, 'tokens_left': current_user.tokens})

@app.route('/process-videos',methods=['POST'])
@login_required
def process_videos():
    vids = request.files.getlist('videos')
    batch = int(request.form.get('batch_size', 5))
    intensity = int(request.form.get('intensity', 30))
    opts = {
        'contrast':'adjust_contrast' in request.form,
        'brightness':'adjust_brightness' in request.form,
        'rotate':'rotate' in request.form,
        'crop':'crop' in request.form,
        'flip':'flip_horizontal' in request.form
    }
    ts = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    out = os.path.join('processed', ts)
    os.makedirs(out, exist_ok=True)

    # --- TOKEN CHECK ---
    tokens_needed = len(vids) * batch * 2  # 2 tokens per video variant
    if current_user.tokens < tokens_needed:
        return jsonify({'error': "Not enough tokens", 'tokens_left': current_user.tokens}), 402

    # --- MAIN PROCESSING ---
    process_videos_logic(
        vids, batch, intensity, opts,
        out=out,
        hist_folder='static/history'
    )

    # --- DEDUCT TOKENS ---
    deduct_tokens(current_user, tokens_needed, db)

    zip_fn = f"videos_{ts}.zip"
    zp = os.path.join('static/processed_zips', zip_fn)
    with zipfile.ZipFile(zp, 'w') as zf:
        for f in os.listdir(out):
            zf.write(os.path.join(out, f), arcname=f)
    shutil.rmtree(out)
    if current_user.backup_enabled:
        upload_to_google_drive(zp, zip_fn)
    return jsonify({'zip_filename': zip_fn, 'tokens_left': current_user.tokens})

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
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

# -------------------- tokens left real time --------------------
@app.route('/tokens-left')
@login_required
def tokens_left():
    return jsonify({'tokens_left': current_user.tokens})
