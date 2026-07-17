import yt_dlp
import os

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def download_media(url):
    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
        'format': 'best',
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info)

    caption = (
        info.get('description')
        or info.get('title')
        or info.get('alt_title')
        or ""
    )
    caption = caption.strip()

    if filepath.endswith(('.jpg', '.jpeg', '.png', '.webp')):
        return filepath, "photo", caption
    return filepath, "video", caption
