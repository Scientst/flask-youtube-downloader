from flask import Flask, request, jsonify, render_template, send_file, Response
from flask_cors import CORS
import yt_dlp
import os
import time
import re
import zipfile
import logging

app = Flask(__name__)
CORS(app)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Path to cookies file (assumed in project root)
COOKIES_FILE = 'youtube_cookies.txt'

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
                <lastmod>2025-03-06</lastmod>
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
        'extract_flat': True,  # Use flat extraction for playlists to avoid deep processing here
    }
    if os.path.exists(COOKIES_FILE):
        ydl_opts['cookiefile'] = COOKIES_FILE
        logger.info(f"Using cookies from {COOKIES_FILE}")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                is_playlist = True
                title = info.get('title', 'Untitled Playlist')
                # Use the first valid entry's thumbnail, or a fallback
                thumbnail = next((entry.get('thumbnail') for entry in info['entries'] if entry and entry.get('thumbnail')), '')
                logger.info(f"Playlist detected: {title}, {len(info['entries'])} entries")
            else:
                is_playlist = False
                title = info.get('title', 'Untitled Video')
                thumbnail = info.get('thumbnail', '')
                logger.info(f"Single video detected: {title}")

            return jsonify({
                'success': True,
                'title': title,
                'thumbnail': thumbnail,
                'is_playlist': is_playlist
            })
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"DownloadError in check_video: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error in check_video: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to process URL. The playlist may contain restricted or unavailable videos.'}), 500

@app.route('/get_playlist_titles', methods=['POST'])
def get_playlist_titles():
    url = request.form.get('url')
    logger.info(f"Fetching playlist titles for URL: {url}")
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,  # Flat extraction for titles
        }
        if os.path.exists(COOKIES_FILE):
            ydl_opts['cookiefile'] = COOKIES_FILE
            logger.info(f"Using cookies from {COOKIES_FILE}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                titles = [entry.get('title', 'Untitled') for entry in info['entries'] if entry]
                logger.info(f"Playlist titles fetched: {len(titles)} titles")
                return jsonify({'success': True, 'titles': titles})
            return jsonify({'success': False, 'error': 'Not a playlist'})
    except Exception as e:
        logger.error(f"Get playlist titles failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

def download_progress_hook(d):
    if d['status'] == 'finished':
        logger.info(f"Download finished: {d.get('filename', 'Unknown')}")
    elif d['status'] == 'downloading':
        logger.debug(f"Downloading: {d.get('filename', 'Unknown')} - {d.get('downloaded_bytes', 0)} bytes")
    elif d['status'] == 'error':
        logger.error(f"Download error: {d.get('error', 'Unknown error')}")

def sanitize_filename(filename):
    filename = re.sub(r'[^\x00-\x7F]+', '_', filename)
    filename = filename.replace(':', '-').replace(' ', '_')
    return filename

@app.route('/download', methods=['GET'])
def download():
    url = request.args.get('url')
    format_type = request.args.get('format', 'mp4')
    quality = request.args.get('quality', 'best')
    is_playlist = request.args.get('is_playlist', 'false') == 'true'

    if not url:
        logger.error("No URL provided")
        return jsonify({'success': False, 'error': 'No URL provided'}), 400

    download_dir = 'downloads'
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
        logger.info(f"Created download directory: {download_dir}")

    ydl_opts = {
        'outtmpl': f'{download_dir}/%(title)s.%(ext)s',
        'noplaylist': not is_playlist,
        'progress_hooks': [download_progress_hook],
        'retries': 10,
        'fragment_retries': 10,
        'quiet': True,
        'no_warnings': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }
    if os.path.exists(COOKIES_FILE):
        ydl_opts['cookiefile'] = COOKIES_FILE
        logger.info(f"Using cookies from {COOKIES_FILE}")

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
        if quality == 'best':
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
        else:
            ydl_opts['format'] = f'bestvideo[height<={quality[:-1]}]+bestaudio/best'
        ydl_opts['merge_output_format'] = 'mp4'

    downloaded_files = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Starting download for URL: {url}, Playlist: {is_playlist}")
            info = ydl.extract_info(url, download=True)
            logger.info("Download completed, processing files")

            if is_playlist and 'entries' in info:
                files = []
                for entry in info['entries']:
                    if not entry:
                        logger.warning("Skipping invalid playlist entry")
                        continue
                    filename = entry.get('requested_downloads', [{}])[0].get('filepath') or ydl.prepare_filename(entry)
                    if format_type == 'mp3':
                        filename = filename.rsplit('.', 1)[0] + '.mp3'
                    if os.path.exists(filename):
                        files.append(filename)
                        downloaded_files.append(filename)
                        logger.info(f"Added to playlist: {filename}")
                    else:
                        logger.warning(f"File not found for playlist entry: {filename}")

                if not files:
                    raise Exception("No files were downloaded for the playlist. The content may be restricted or unavailable.")

                zip_filename = f"{download_dir}/playlist_{int(time.time())}.zip"
                with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file in files:
                        zipf.write(file, os.path.basename(file))
                        logger.info(f"Zipped file: {file}")
                downloaded_files.append(zip_filename)

                logger.info(f"Sending playlist ZIP: {zip_filename}")
                response = send_file(
                    zip_filename,
                    as_attachment=True,
                    mimetype='application/zip'
                )
                response.headers['Content-Disposition'] = f'attachment; filename="{sanitize_filename(os.path.basename(zip_filename))}"'
                return response
            else:
                filename = info.get('requested_downloads', [{}])[0].get('filepath') or ydl.prepare_filename(info)
                if format_type == 'mp3':
                    filename = filename.rsplit('.', 1)[0] + '.mp3'

                for _ in range(10):
                    if os.path.exists(filename) and os.path.getsize(filename) > 0:
                        logger.info(f"File ready: {filename}")
                        break
                    logger.debug(f"Waiting for file: {filename}")
                    time.sleep(1)

                if not os.path.exists(filename) or os.path.getsize(filename) == 0:
                    raise Exception(f"File not found or empty: {filename}")

                downloaded_files.append(filename)
                sanitized_filename = sanitize_filename(os.path.basename(filename))
                logger.info(f"Sending single file: {filename}")
                response = send_file(
                    filename,
                    as_attachment=True,
                    mimetype='application/octet-stream' if format_type == 'mp3' else 'video/mp4'
                )
                response.headers['Content-Disposition'] = f'attachment; filename="{sanitized_filename}"'
                return response
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"yt_dlp error: {str(e)}")
        if "Sign in to confirm" in str(e):
            return jsonify({'success': False, 'error': 'Authentication required. Please check if the cookies file is valid and up-to-date.'}), 403
        return jsonify({'success': False, 'error': str(e)}), 500
    except Exception as e:
        logger.error(f"General error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        for file in downloaded_files:
            if os.path.exists(file):
                try:
                    os.remove(file)
                    logger.info(f"Cleaned up: {file}")
                except Exception as e:
                    logger.error(f"Failed to remove {file}: {e}")
        if os.path.exists(download_dir) and not os.listdir(download_dir):
            try:
                os.rmdir(download_dir)
                logger.info(f"Removed empty directory: {download_dir}")
            except Exception as e:
                logger.error(f"Failed to remove {download_dir}: {e}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)