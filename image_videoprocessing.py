import os
import random
import shutil
from PIL import Image, ImageEnhance
import ffmpeg
import sys
import traceback

import piexif
import piexif.helper
from metadata_words import random_exif_fields

def rational_from_float(val):
    # Convert float to EXIF rational (num, den)
    deg = int(abs(val))
    min_ = int((abs(val) - deg) * 60)
    sec = int((((abs(val) - deg) * 60) - min_) * 60 * 100)
    return ((deg, 1), (min_, 1), (sec, 100))

def randomize_image_exif(img):
    exif_data = random_exif_fields()
    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

    # 0th IFD
    exif_dict["0th"][piexif.ImageIFD.Artist] = exif_data["artist"].encode()
    exif_dict["0th"][piexif.ImageIFD.ImageDescription] = exif_data["description"].encode()
    exif_dict["0th"][piexif.ImageIFD.Copyright] = exif_data["copyright"].encode()
    exif_dict["0th"][piexif.ImageIFD.DateTime] = exif_data["datetime"].encode()

    # GPS IFD
    lat = exif_data["gps_lat"]
    lon = exif_data["gps_lon"]
    exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = b'N' if lat >= 0 else b'S'
    exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = rational_from_float(lat)
    exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b'E' if lon >= 0 else b'W'
    exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = rational_from_float(lon)
    
    # Save to BytesIO to attach exif
    import io
    output = io.BytesIO()
    img.save(output, format="JPEG", exif=piexif.dump(exif_dict))
    output.seek(0)
    return Image.open(output)

# ... rest of your code (scale_range, process_images_logic, etc)

OUTPUT_FOLDER = "output"
HISTORY_FOLDER = "history"

# Ensure output/history folders exist
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(HISTORY_FOLDER, exist_ok=True)

def scale_range(min_val, max_val, intensity):
    return random.uniform(min_val * (intensity / 100), max_val * (intensity / 100))

def process_images_logic(images, batch, intensity, opts, out=OUTPUT_FOLDER, hist_folder=HISTORY_FOLDER):
    for img_file in images:
        try:
            print(f"Opening image file: {img_file.filename}", file=sys.stderr)
            img = Image.open(img_file)
            name = os.path.splitext(img_file.filename)[0]
            for i in range(batch):
                var = img.copy()
                if opts.get('contrast'):
                    var = ImageEnhance.Contrast(var).enhance(1 + scale_range(-0.1, 0.1, intensity))
                if opts.get('brightness'):
                    var = ImageEnhance.Brightness(var).enhance(1 + scale_range(-0.1, 0.1, intensity))
                if opts.get('rotate'):
                    var = var.rotate(scale_range(-5, 5, intensity), expand=True)
                if opts.get('crop'):
                    w, h = var.size
                    dx, dy = int(w * scale_range(0.01, 0.05, intensity)), int(h * scale_range(0.01, 0.05, intensity))
                    var = var.crop((dx, dy, w - dx, h - dy))
                if opts.get('flip') and random.random() > 0.5:
                    var = var.transpose(Image.FLIP_LEFT_RIGHT)

                # Decide on file extension and format based on image mode
                if var.mode in ("RGBA", "LA") or (var.mode == "P" and "transparency" in var.info):
                    fn = f"{name}_variant_{i+1}.png"
                    out_path = os.path.join(out, fn)
                    hist_path = os.path.join(hist_folder, fn)
                    var.save(out_path, format="PNG")
                    var.save(hist_path, format="PNG")
                else:
                    fn = f"{name}_variant_{i+1}.jpg"
                    out_path = os.path.join(out, fn)
                    hist_path = os.path.join(hist_folder, fn)
                    img_to_save = var.convert("RGB")
                    if opts.get('metadata'):
                        img_to_save = randomize_image_exif(img_to_save)
                    img_to_save.save(out_path, format="JPEG")
                    img_to_save.save(hist_path, format="JPEG")
        except Exception as e:
            print(f"Exception processing image {img_file.filename}: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            raise

def process_videos_logic(vids, batch, intensity, opts, out=OUTPUT_FOLDER, hist_folder=HISTORY_FOLDER):
    for vf in vids:
        try:
            src = os.path.join('uploads', vf.filename)
            print(f"Saving uploaded video file {vf.filename} to {src}", file=sys.stderr)
            vf.save(src)
            print("File saved.", file=sys.stderr)
            probe = ffmpeg.probe(src)
            print(f"ffmpeg probe result: {probe}", file=sys.stderr)
            vs = next(s for s in probe['streams'] if s['codec_type'] == 'video')
            w, h = int(vs['width']), int(vs['height'])
            name = os.path.splitext(vf.filename)[0]
            for i in range(batch):
                outp = os.path.join(out, f"{name}_variant_{i+1}.mp4")
                hist = os.path.join(hist_folder, f"{name}_variant_{i+1}.mp4")
                st = ffmpeg.input(src)
                
                # Contrast & Brightness
                c = 1 + scale_range(-0.1, 0.1, intensity) if opts.get('contrast') else 1
                b = scale_range(-0.05, 0.05, intensity) if opts.get('brightness') else 0
                if opts.get('contrast') or opts.get('brightness'):
                    print(f"Applying eq filter with contrast={c}, brightness={b}", file=sys.stderr)
                    st = st.filter('eq', contrast=c, brightness=b)
                
                # Rotation
                if opts.get('rotate'):
                    angle_degrees = scale_range(-5, 5, intensity)
                    angle_rads = angle_degrees * 3.1415926 / 180
                    print(f"Applying rotate filter with angle (rads): {angle_rads}", file=sys.stderr)
                    st = st.filter('rotate', angle=angle_rads, fillcolor='black')
                
                # Crop (then scale back to original size)
                if opts.get('crop'):
                    dx = int(w * scale_range(0.01, 0.05, intensity))
                    dy = int(h * scale_range(0.01, 0.05, intensity))
                    print(f"Applying crop filter: dx={dx}, dy={dy}", file=sys.stderr)
                    st = st.filter('crop', w - 2 * dx, h - 2 * dy, dx, dy).filter('scale', w, h)
                
                # Horizontal flip (randomly, like images)
                if opts.get('flip') and random.random() > 0.5:
                    print("Applying hflip filter", file=sys.stderr)
                    st = st.filter('hflip')

                cmd = ffmpeg.output(st, outp, vcodec='libx264', acodec='aac')
                try:
                    ffmpeg.run(cmd, overwrite_output=True)
                    print("ffmpeg ran successfully.", file=sys.stderr)
                except ffmpeg.Error as e:
                    print("ffmpeg exception:", e, file=sys.stderr)
                    print("ffmpeg stdout:\n", e.stdout.decode() if e.stdout else repr(e.stdout), file=sys.stderr)
                    print("ffmpeg stderr:\n", e.stderr.decode() if e.stderr else repr(e.stderr), file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    raise
                except Exception as e:
                    print("General exception in ffmpeg logic:", e, file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    raise
                print(f"Copying output to history: {hist}", file=sys.stderr)
                shutil.copy(outp, hist)
            print(f"Removing source file {src}", file=sys.stderr)
            os.remove(src)
        except Exception as e:
            print(f"Exception in process_videos_logic for video {vf.filename}: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            raise
