from flask import Flask, request, jsonify, render_template, send_file, Response
from flask_cors import CORS
import yt_dlp
import os
import time
import re
import zipfile

app = Flask(__name__)
CORS(app)

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
    print(f"Checking video info for URL: {url}")
    
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if 'entries' in info:
                is_playlist = True
                title = info['title']
                thumbnail = info['entries'][0]['thumbnail']
            else:
                is_playlist = False
                title = info['title']
                thumbnail = info['thumbnail']
                
            return jsonify({
                'success': True,
                'title': title,
                'thumbnail': thumbnail,
                'is_playlist': is_playlist
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get_playlist_titles', methods=['POST'])
def get_playlist_titles():
    url = request.form.get('url')
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                titles = [entry['title'] for entry in info['entries']]
                return jsonify({'success': True, 'titles': titles})
            return jsonify({'success': False, 'error': 'Not a playlist'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def download_progress_hook(d):
    if d['status'] == 'finished':
        print(f"Finished downloading: {d['filename']}")
    elif d['status'] == 'error':
        print(f"Error during download: {d.get('error')}")
        part_file = d.get('filename', '') + '.part'
        if os.path.exists(part_file):
            try:
                os.remove(part_file)
            except Exception as e:
                print(f"Failed to remove partial file: {e}")

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
        return jsonify({'success': False, 'error': 'No URL provided'}), 400

    download_dir = 'downloads'
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    ydl_opts = {
        'outtmpl': f'{download_dir}/%(title)s.%(ext)s',
        'noplaylist': not is_playlist,
        'progress_hooks': [download_progress_hook],
        'retries': 10,  # Increased retries for reliability
        'fragment_retries': 10,
        'quiet': True,  # Suppress excessive output
        'no_warnings': True,  # Reduce noise
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',  # Keep User-Agent
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
        if quality == 'best':
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
        else:
            ydl_opts['format'] = f'bestvideo[height<={quality[:-1]}]+bestaudio/best'
        ydl_opts['merge_output_format'] = 'mp4'

    downloaded_files = []  # Track files for cleanup
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if is_playlist and 'entries' in info:
                files = []
                for entry in info['entries']:
                    if entry is None:  # Skip failed entries
                        continue
                    # Use the actual downloaded filename if available
                    filename = entry.get('_filename')
                    if not filename:
                        filename = ydl.prepare_filename(entry)
                    if format_type == 'mp3':
                        filename = filename.rsplit('.', 1)[0] + '.mp3'
                    if os.path.exists(filename):
                        files.append(filename)
                        downloaded_files.append(filename)
                    else:
                        print(f"Warning: Expected file not found - {filename}")

                if not files:
                    raise Exception("No files downloaded for playlist. The content may be restricted or unavailable.")

                zip_filename = f"{download_dir}/playlist_{int(time.time())}.zip"
                with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file in files:
                        zipf.write(file, os.path.basename(file))
                downloaded_files.append(zip_filename)

                response = send_file(
                    zip_filename,
                    as_attachment=True,
                    mimetype='application/zip'
                )
                response.headers['Content-Disposition'] = f'attachment; filename="{sanitize_filename(os.path.basename(zip_filename))}"'
                return response
            else:
                filename = info.get('_filename')
                if not filename:
                    filename = ydl.prepare_filename(info)
                if format_type == 'mp3':
                    filename = filename.rsplit('.', 1)[0] + '.mp3'

                # Wait for file to be fully written
                for _ in range(10):  # Increased timeout
                    if os.path.exists(filename) and os.path.getsize(filename) > 0:
                        try:
                            with open(filename, 'rb') as f:
                                f.read(1)  # Test file accessibility
                            break
                        except IOError:
                            time.sleep(1)
                    else:
                        time.sleep(1)

                if not os.path.exists(filename) or os.path.getsize(filename) == 0:
                    raise Exception(f"File not found or empty after download: {filename}")

                downloaded_files.append(filename)
                sanitized_filename = sanitize_filename(os.path.basename(filename))
                response = send_file(
                    filename,
                    as_attachment=True,
                    mimetype='application/octet-stream' if format_type == 'mp3' else 'video/mp4'
                )
                response.headers['Content-Disposition'] = f'attachment; filename="{sanitized_filename}"'
                return response
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if "Sign in to confirm" in error_msg:
            return jsonify({'success': False, 'error': 'This content requires authentication. Please try a publicly accessible URL.'}), 403
        elif "unavailable" in error_msg.lower() or "private" in error_msg.lower():
            return jsonify({'success': False, 'error': 'The video or playlist is unavailable or private.'}), 404
        print(f"Download error: {error_msg}")
        return jsonify({'success': False, 'error': error_msg}), 500
    except Exception as e:
        error_msg = str(e)
        print(f"Unexpected error: {error_msg}")
        return jsonify({'success': False, 'error': error_msg}), 500
    finally:
        # Clean up all downloaded files
        for file in downloaded_files:
            if os.path.exists(file):
                try:
                    os.remove(file)
                except Exception as e:
                    print(f"Failed to remove file {file}: {e}")
        if os.path.exists(download_dir) and not os.listdir(download_dir):
            try:
                os.rmdir(download_dir)
            except Exception as e:
                print(f"Failed to remove directory {download_dir}: {e}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
