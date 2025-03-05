from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
import yt_dlp
import os

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

@app.route('/download', methods=['GET'])
def download():
    url = request.args.get('url')
    format_type = request.args.get('format', 'mp4')  # Default to mp4
    quality = request.args.get('quality', 'best')    # Default to best
    
    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'}), 400

    ydl_opts = {
        'outtmpl': 'downloads/%(title)s.%(ext)s',
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
            filename = ydl.prepare_filename(info)
            if format_type == 'mp3':
                # Adjust filename extension for MP3
                filename = filename.rsplit('.', 1)[0] + '.mp3'

        return send_file(filename, as_attachment=True)

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    app.run(debug=True)