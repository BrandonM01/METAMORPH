import os
import random
import shutil
from PIL import Image, ImageEnhance
import ffmpeg
import sys
import traceback
import math

OUTPUT_FOLDER = "output"
HISTORY_FOLDER = "history"

# Ensure output/history folders exist
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(HISTORY_FOLDER, exist_ok=True)

def scale_range(min_val, max_val, intensity):
    # At intensity=100, uses the full range; at lower, scales down.
    factor = intensity / 100
    return random.uniform(min_val * factor, max_val * factor)

def param_distance(a, b):
    # Simple Euclidean distance; tune with weights if desired
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

def is_unique(params, used_params, min_dist=0.07):
    for up in used_params:
        if param_distance(params, up) < min_dist:
            return False
    return True

def process_images_logic(images, batch, intensity, opts, out=OUTPUT_FOLDER, hist_folder=HISTORY_FOLDER):
    # Adjust these values as needed for your use case/platform
    contrast_min, contrast_max = -4.0, 4.0
    brightness_min, brightness_max = -2, 2
    rotation_min, rotation_max = -25, 25
    crop_min, crop_max = 0.15, 0.35  # 5%–15% crop

    for img_file in images:
        try:
            print(f"Opening image file: {img_file.filename}", file=sys.stderr)
            img = Image.open(img_file)
            name = os.path.splitext(img_file.filename)[0]
            used_params = []
            for i in range(batch):
                tries = 0
                while True:
                    contrast = scale_range(contrast_min, contrast_max, intensity) if opts.get('contrast') else 0
                    brightness = scale_range(brightness_min, brightness_max, intensity) if opts.get('brightness') else 0
                    rotation = scale_range(rotation_min, rotation_max, intensity) if opts.get('rotate') else 0
                    crop_factor = scale_range(crop_min, crop_max, intensity) if opts.get('crop') else 0
                    params = (round(contrast, 3), round(brightness, 3), round(rotation, 2), round(crop_factor, 3))
                    if is_unique(params, used_params):
                        used_params.append(params)
                        break
                    tries += 1
                    if tries > 50:
                        print("Warning: couldn't find unique params after 50 tries!")
                        break
                var = img.copy()
                if opts.get('contrast'):
                    var = ImageEnhance.Contrast(var).enhance(1 + contrast)
                if opts.get('brightness'):
                    var = ImageEnhance.Brightness(var).enhance(1 + brightness)
                if opts.get('rotate'):
                    var = var.rotate(rotation, expand=True)
                if opts.get('crop'):
                    w, h = var.size
                    dx, dy = int(w * crop_factor), int(h * crop_factor)
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
                    var.convert("RGB").save(out_path, format="JPEG")
                    var.convert("RGB").save(hist_path, format="JPEG")
        except Exception as e:
            print(f"Exception processing image {img_file.filename}: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            raise

def process_videos_logic(vids, batch, intensity, opts, out=OUTPUT_FOLDER, hist_folder=HISTORY_FOLDER):
    # Adjust these values as needed for your use case/platform
    contrast_min, contrast_max = -4.0, 4.0
    brightness_min, brightness_max = -2, 2
    rotation_min, rotation_max = -25, 25
    crop_min, crop_max = 0.10, 0.35  # 5%–15% crop

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
            used_params = []
            for i in range(batch):
                tries = 0
                while True:
                    contrast = scale_range(contrast_min, contrast_max, intensity) if opts.get('contrast') else 0
                    brightness = scale_range(brightness_min, brightness_max, intensity) if opts.get('brightness') else 0
                    rotation = scale_range(rotation_min, rotation_max, intensity) if opts.get('rotate') else 0
                    crop_factor = scale_range(crop_min, crop_max, intensity) if opts.get('crop') else 0
                    params = (round(contrast, 3), round(brightness, 3), round(rotation, 2), round(crop_factor, 3))
                    if is_unique(params, used_params):
                        used_params.append(params)
                        break
                    tries += 1
                    if tries > 50:
                        print("Warning: couldn't find unique params after 50 tries!")
                        break
                outp = os.path.join(out, f"{name}_variant_{i+1}.mp4")
                hist = os.path.join(hist_folder, f"{name}_variant_{i+1}.mp4")
                st = ffmpeg.input(src)

                # Contrast & Brightness
                c = 1 + contrast if opts.get('contrast') else 1
                b = brightness if opts.get('brightness') else 0
                if opts.get('contrast') or opts.get('brightness'):
                    print(f"Applying eq filter with contrast={c}, brightness={b}", file=sys.stderr)
                    st = st.filter('eq', contrast=c, brightness=b)

                # Rotation
                if opts.get('rotate'):
                    angle_rads = rotation * 3.1415926 / 180
                    print(f"Applying rotate filter with angle (rads): {angle_rads}", file=sys.stderr)
                    st = st.filter('rotate', angle=angle_rads, fillcolor='black')

                # Crop (then scale back to original size)
                if opts.get('crop'):
                    dx = int(w * crop_factor)
                    dy = int(h * crop_factor)
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
