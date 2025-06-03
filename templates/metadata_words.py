import random
from datetime import datetime, timedelta

METADATA_WORDS = {
    "title": [
        "Sunset Memory", "Urban Adventure", "Wandering Spirit", "Dreamscape", "Golden Hour", "Electric Night"
    ],
    "author": [
        "Alex Rivers", "Jamie Lee", "Taylor Morgan", "Jordan Blake", "Sam Casey", "Morgan Lane"
    ],
    "description": [
        "A vivid scene.", "Captured moment.", "A colorful story.", "Vivid vision.", "Unforgettable journey.", "Mysterious landscape."
    ],
    "custom": [
        "projectX", "session42", "tag_random", "uniqueBatch", "hiddenGem", "midnightEdit"
    ],
}

def random_gps():
    # MP4 expects ISO6709, EXIF expects rational (see below)
    lat = random.uniform(-90, 90)
    lon = random.uniform(-180, 180)
    return f"{lat:+08.4f}{lon:+09.4f}/"

def random_date():
    # Random date in the last 10 years
    start = datetime.now() - timedelta(days=365*10)
    random_days = random.randint(0, 365*10)
    rand_dt = start + timedelta(days=random_days, seconds=random.randint(0, 86400))
    return rand_dt.strftime('%Y-%m-%dT%H:%M:%S')

def random_metadata_fields():
    return {
        "title": random.choice(METADATA_WORDS["title"]),
        "artist": random.choice(METADATA_WORDS["author"]),
        "comment": random.choice(METADATA_WORDS["description"]),
        "description": random.choice(METADATA_WORDS["description"]),
        "album": random.choice(METADATA_WORDS["custom"]),
        "date": random_date(),
        "location": random_gps(),
        "creation_time": random_date(),
    }

def random_exif_fields():
    return {
        "artist": random.choice(METADATA_WORDS["author"]),
        "description": random.choice(METADATA_WORDS["description"]),
        "copyright": random.choice(METADATA_WORDS["custom"]),
        "datetime": random_date().replace("T", " "),
        "gps_lat": random.uniform(-90, 90),
        "gps_lon": random.uniform(-180, 180),
    }
