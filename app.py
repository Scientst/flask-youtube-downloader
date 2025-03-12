from flask import Flask, request, jsonify, render_template, send_file, Response, stream_with_context
from flask_cors import CORS
import yt_dlp
import os
import time
import re
import zipfile
import logging
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # Allow all origins for simplicity

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

COOKIES_FILE = 'youtube_cookies.txt'
DOWNLOAD_DIR = 'downloads'

def ensure_download_dir():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
        logger.info(f"Created download directory: {DOWNLOAD_DIR}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/robots.txt')
def robots_txt():
    return Response(
        "User-agent: *\nAllow: /\nSitemap: https://ytgenie-youtube-downloader.onrender.com/sitemap.xml",
        mimetype="text/plain"
    )

@app.route('/sitemap.xml')
def sitemap():
    return Response(
        '''<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url>
                <loc>https://ytgenie-youtube-downloader.onrender.com/</loc>
                <lastmod>2025-03-12</lastmod>
                <changefreq>monthly</changefreq>
                <priority>1.0</priority>
            </url>
        </urlset>''',
        mimetype="application/xml"
    )

@app.route('/check_video', methods=['POST'])
def check_video():
    url = request.form.get('url')
    logger.info(f"Checking video info for URL: {url}")
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise Exception("Invalid URL or authentication required.")
            is_playlist = 'entries' in info
            title = info.get('title', 'Untitled') if not is_playlist else info.get('title', 'Untitled Playlist')
            thumbnail = info.get('thumbnail') or (info['entries'][0].get('thumbnail') if is_playlist and info['entries'] else 'https://via.placeholder.com/150?text=No+Thumbnail')
            return jsonify({
                'success': True,
                'title': title,
                'thumbnail': thumbnail,
                'is_playlist': is_playlist
            })
    except Exception as e:
        logger.error(f"Error in check_video: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/get_playlist_titles', methods=['POST'])
def get_playlist_titles():
    url = request.form.get('url')
    logger.info(f"Fetching playlist titles for URL: {url}")
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                titles = [entry.get('title', 'Untitled') for entry in info['entries'] if entry]
                return jsonify({'success': True, 'titles': titles})
            return jsonify({'success': False, 'error': 'Not a playlist'})
    except Exception as e:
        logger.error(f"Error in get_playlist_titles: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

def download_progress_hook(d):
    if d['status'] == 'finished':
        logger.info(f"Download finished: {d.get('filename', 'Unknown')}")
    elif d['status'] == 'error':
        logger.error(f"Download error: {d.get('error', 'Unknown error')}")

def sanitize_filename(filename):
    return secure_filename(re.sub(r'[^\x00-\x7F]+', '_', filename.replace(':', '-').replace(' ', '_')))

@app.route('/download', methods=['GET'])
def download():
    url = request.args.get('url')
    format_type = request.args.get('format', 'mp4')
    quality = request.args.get('quality', 'best')
    is_playlist = request.args.get('is_playlist', 'false') == 'true'

    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'}), 400

    ensure_download_dir()
    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'noplaylist': not is_playlist,
        'progress_hooks': [download_progress_hook],
        'retries': 10,
        'fragment_retries': 10,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        'ffmpeg_location': '/usr/bin/ffmpeg',  # Adjust if needed
    }

    if format_type == 'mp3':
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    else:
        ydl_opts['merge_output_format'] = 'mp4'
        ydl_opts['format'] = 'bestvideo+bestaudio/best' if quality == 'best' else f'bestvideo[height<={quality[:-1]}]+bestaudio/best'

    downloaded_files = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise Exception("Download failed. Check URL or authentication.")

            if is_playlist and 'entries' in info:
                files = []
                for entry in info['entries']:
                    if entry and 'requested_downloads' in entry:
                        filepath = entry['requested_downloads'][0].get('filepath') or ydl.prepare_filename(entry)
                        if format_type == 'mp3':
                            filepath = filepath.rsplit('.', 1)[0] + '.mp3'
                        for _ in range(5):
                            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                                files.append(filepath)
                                downloaded_files.append(filepath)
                                break
                            time.sleep(1)

                if not files:
                    raise Exception("No files downloaded for playlist.")

                zip_filename = f"{DOWNLOAD_DIR}/playlist_{int(time.time())}.zip"
                with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file in files:
                        zipf.write(file, os.path.basename(file))

                downloaded_files.append(zip_filename)

                def generate():
                    with open(zip_filename, 'rb') as f:
                        while chunk := f.read(8192):
                            yield chunk
                    # Cleanup after streaming
                    for file in downloaded_files:
                        if os.path.exists(file):
                            os.remove(file)
                    if not os.listdir(DOWNLOAD_DIR):
                        os.rmdir(DOWNLOAD_DIR)

                response = Response(stream_with_context(generate()), mimetype='application/zip')
                response.headers['Content-Disposition'] = f'attachment; filename="{sanitize_filename(os.path.basename(zip_filename))}"'
                response.headers['Content-Length'] = os.path.getsize(zip_filename)
                return response
            else:
                filepath = info['requested_downloads'][0].get('filepath') or ydl.prepare_filename(info)
                if format_type == 'mp3':
                    filepath = filepath.rsplit('.', 1)[0] + '.mp3'
                for _ in range(5):
                    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                        break
                    time.sleep(1)

                if not os.path.exists(filepath):
                    raise Exception("File not downloaded.")

                downloaded_files.append(filepath)
                mimetype = 'audio/mpeg' if format_type == 'mp3' else 'video/mp4'

                def generate():
                    with open(filepath, 'rb') as f:
                        while chunk := f.read(8192):
                            yield chunk
                    # Cleanup after streaming
                    for file in downloaded_files:
                        if os.path.exists(file):
                            os.remove(file)
                    if not os.listdir(DOWNLOAD_DIR):
                        os.rmdir(DOWNLOAD_DIR)

                response = Response(stream_with_context(generate()), mimetype=mimetype)
                response.headers['Content-Disposition'] = f'attachment; filename="{sanitize_filename(os.path.basename(filepath))}"'
                response.headers['Content-Length'] = os.path.getsize(filepath)
                return response
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)