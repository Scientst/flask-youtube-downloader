from flask import Flask, request, jsonify, render_template, send_file, Response
from flask_cors import CORS
import yt_dlp
import os
import time
import re

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return render_template('index.html')

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

def download_progress_hook(d):
    """Hook to handle yt-dlp progress and file cleanup."""
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
    """Remove or replace characters that can't be encoded in Latin-1."""
    filename = re.sub(r'[^\x00-\x7F]+', '_', filename)  # Replace non-ASCII with underscore
    filename = filename.replace(':', '-')  # Replace colon with dash
    filename = filename.replace(' ', '_')  # Replace spaces with underscores
    return filename

@app.route('/download', methods=['GET'])
def download():
    url = request.args.get('url')
    format_type = request.args.get('format', 'mp4')
    quality = request.args.get('quality', 'best')
    is_playlist = request.args.get('is_playlist', 'false') == 'true'

    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'}), 400

    ydl_opts = {
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'noplaylist': not is_playlist,
        'progress_hooks': [download_progress_hook],
        'retries': 3,
        'fragment_retries': 3,
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
    else:  # mp4
        if quality == 'best':
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
        else:
            ydl_opts['format'] = f'bestvideo[height<={quality[:-1]}]+bestaudio/best'
        ydl_opts['merge_output_format'] = 'mp4'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if is_playlist and 'entries' in info:
                filename = ydl.prepare_filename(info['entries'][0])
            else:
                filename = ydl.prepare_filename(info)
            if format_type == 'mp3':
                filename = filename.rsplit('.', 1)[0] + '.mp3'

            for _ in range(5):
                if os.path.exists(filename):
                    try:
                        with open(filename, 'rb') as f:
                            f.read(1)
                        break
                    except IOError:
                        time.sleep(1)
                else:
                    time.sleep(1)

            if not os.path.exists(filename):
                raise Exception("File not found after download")

        sanitized_filename = sanitize_filename(os.path.basename(filename))
        response = send_file(
            filename,
            as_attachment=True,
            mimetype='application/octet-stream' if format_type == 'mp3' else 'video/mp4'
        )
        response.headers['Content-Disposition'] = f'attachment; filename="{sanitized_filename}"'
        return response
    except Exception as e:
        for ext in ['.part', '.f398.mp4', '.f251.webm']:
            temp_file = filename + ext if 'filename' in locals() else f'downloads/temp{ext}'
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    app.run(debug=True)