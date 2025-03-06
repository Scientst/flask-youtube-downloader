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
    else:
        if quality == 'best':
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
        else:
            ydl_opts['format'] = f'bestvideo[height<={quality[:-1]}]+bestaudio/best'
        ydl_opts['merge_output_format'] = 'mp4'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if is_playlist and 'entries' in info:
                files = []
                for entry in info['entries']:
                    filename = ydl.prepare_filename(entry)
                    if format_type == 'mp3':
                        filename = filename.rsplit('.', 1)[0] + '.mp3'
                    if os.path.exists(filename):
                        files.append(filename)
                
                if not files:
                    raise Exception("No files downloaded for playlist")
                
                zip_filename = f"{download_dir}/playlist_{int(time.time())}.zip"
                with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file in files:
                        zipf.write(file, os.path.basename(file))
                
                response = send_file(
                    zip_filename,
                    as_attachment=True,
                    mimetype='application/zip'
                )
                response.headers['Content-Disposition'] = f'attachment; filename="{sanitize_filename(os.path.basename(zip_filename))}"'
                
                for file in files:
                    try:
                        os.remove(file)
                    except:
                        pass
                return response
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
            temp_file = (filename + ext if 'filename' in locals() else f'{download_dir}/temp{ext}')
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if 'zip_filename' in locals() and os.path.exists(zip_filename):
            try:
                os.remove(zip_filename)
            except:
                pass

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)