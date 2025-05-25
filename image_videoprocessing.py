import os
import random
import shutil
import zipfile
import datetime
from PIL import Image, ImageEnhance
import ffmpeg
import sys

def scale_range(min_val, max_val, intensity):
    return random.uniform(min_val * (intensity / 100), max_val * (intensity / 100))

def process_images_logic(images, batch, intensity, opts, out, hist_folder):
    for img_file in images:
        img = Image.open(img_file)
        name = os.path.splitext(img_file.filename)[0]
        for i in range(batch):
            var = img.copy()
            if opts['contrast']:
                var = ImageEnhance.Contrast(var).enhance(1 + scale_range(-0.1, 0.1, intensity))
            if opts['brightness']:
                var = ImageEnhance.Brightness(var).enhance(1 + scale_range(-0.1, 0.1, intensity))
            if opts['rotate']:
                var = var.rotate(scale_range(-5, 5, intensity), expand=True)
            if opts['crop']:
                w, h = var.size
                dx, dy = int(w * scale_range(0.01, 0.05, intensity)), int(h * scale_range(0.01, 0.05, intensity))
                var = var.crop((dx, dy, w - dx, h - dy))
            if opts['flip'] and random.random() > 0.5:
                var = var.transpose(Image.FLIP_LEFT_RIGHT)
            fn = f"{name}_variant_{i+1}.jpg"
            var.save(os.path.join(out, fn))
            var.save(os.path.join(hist_folder, fn))

def process_videos_logic(vids, batch, intensity, opts, out, hist_folder):
    for vf in vids:
        src = os.path.join('uploads', vf.filename)
        vf.save(src)
        probe = ffmpeg.probe(src)
        vs = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        w, h = int(vs['width']), int(vs['height'])
        name = os.path.splitext(vf.filename)[0]
        for i in range(batch):
            outp = os.path.join(out, f"{name}_variant_{i+1}.mp4")
            hist = os.path.join(hist_folder, f"{name}_variant_{i+1}.mp4")
            st = ffmpeg.input(src)
            if opts['contrast'] or opts['brightness']:
                c = 1 + scale_range(-0.1, 0.1, intensity) if opts['contrast'] else 1
                b = scale_range(-0.05, 0.05, intensity) if opts['brightness'] else 0
                st = st.filter('eq', contrast=c, brightness=b)
            if opts['rotate']:
                st = st.filter('rotate', scale_range(-2, 2, intensity) * 3.1415 / 180)
            if opts['crop']:
                dx, dy = int(w * scale_range(0.01, 0.03, intensity)), int(h * scale_range(0.01, 0.03, intensity))
                st = st.filter('crop', w - 2 * dx, h - 2 * dy, dx, dy).filter('scale', w, h)
            if opts['flip'] and random.random() > 0.5:
                st = st.filter('hflip')
            try:
                ffmpeg.run(
                    ffmpeg.output(st, outp, vcodec='libx264', acodec='aac'),
                    overwrite_output=True
                )
            except ffmpeg.Error as e:
                print("ffmpeg stdout:\n", e.stdout.decode() if e.stdout else e.stdout, file=sys.stderr)
                print("ffmpeg stderr:\n", e.stderr.decode() if e.stderr else e.stderr, file=sys.stderr)
                raise
            shutil.copy(outp, hist)
        os.remove(src)
