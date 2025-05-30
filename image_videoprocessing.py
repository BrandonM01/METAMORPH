import os
import random
import shutil
from PIL import Image, ImageEnhance
import ffmpeg
import sys
import traceback

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
                fn = f"{name}_variant_{i+1}.jpg"
                out_path = os.path.join(out, fn)
                hist_path = os.path.join(hist_folder, fn)
                print(f"Saving image variant to {out_path} and {hist_path}", file=sys.stderr)
                var_rgb = var.convert("RGB")  # Ensure JPEG compatibility
                var_rgb.save(out_path)
                var_rgb.save(hist_path)
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
                # --- Uncomment and debug filters one at a time if needed ---
                # if opts.get('contrast') or opts.get('brightness'):
                #     c = 1 + scale_range(-0.1, 0.1, intensity) if opts.get('contrast') else 1
                #     b = scale_range(-0.05, 0.05, intensity) if opts.get('brightness') else 0
                #     print(f"Applying eq filter with contrast={c}, brightness={b}", file=sys.stderr)
                #     st = st.filter('eq', contrast=c, brightness=b)
                # if opts.get('rotate'):
                #     angle_rads = scale_range(-2, 2, intensity) * 3.1415 / 180
                #     print(f"Applying rotate filter with angle (rads): {angle_rads}", file=sys.stderr)
                #     st = st.filter('rotate', angle_rads)
                # if opts.get('crop'):
                #     dx, dy = int(w * scale_range(0.01, 0.03, intensity)), int(h * scale_range(0.01, 0.03, intensity))
                #     print(f"Applying crop filter: dx={dx}, dy={dy}", file=sys.stderr)
                #     st = st.filter('crop', w - 2 * dx, h - 2 * dy, dx, dy).filter('scale', w, h)
                # if opts.get('flip') and random.random() > 0.5:
                #     print("Applying hflip filter", file=sys.stderr)
                #     st = st.filter('hflip')
                # ---------------------------------------------------------
                cmd = ffmpeg.output(st, outp, vcodec='libx264', acodec='aac')
                ffmpeg.run(cmd, overwrite_output=True)
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
