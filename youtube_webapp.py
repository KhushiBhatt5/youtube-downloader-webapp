#!/usr/bin/env python3
"""
YouTube Downloader Web App with Live Progress and Zip Download
Downloads go to the user's Downloads folder.
"""

from flask import Flask, render_template_string, request, jsonify, send_file
import os, sys, subprocess, threading, uuid, time, zipfile
from pathlib import Path

app = Flask(__name__)
downloads = {}
downloads_lock = threading.Lock()

# ---------------- Install yt-dlp if missing ----------------
def install_yt_dlp():
    try:
        import yt_dlp
        return True
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
        return True

# ---------------- Validate YouTube URL ----------------
def is_valid_youtube_url(url):
    return "youtube.com" in url or "youtu.be" in url

# ---------------- Download Videos ----------------
def download_videos(urls, download_id, _, quality):
    import yt_dlp

    home = Path.home()
    download_dir = home / "Downloads" / f"YouTube_{download_id}"
    download_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        'outtmpl': str(download_dir / '%(playlist_index)02d - %(title)s.%(ext)s'),
        'format': f'best[height<={quality}]' if quality != 'best' else 'best',
        'ignoreerrors': True,
        'no_warnings': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'progress_hooks': [],
    }

    total = len(urls)
    completed = 0
    errors = []

    def progress_hook(d):
        nonlocal completed
        with downloads_lock:
            if d['status'] == 'downloading':
                downloads[download_id]['progress'] = int((completed / total) * 90)
                downloads[download_id]['current'] = f"Downloading: {d.get('filename','')[:50]}"
            elif d['status'] == 'finished':
                completed += 1
                downloads[download_id]['current'] = f"Finished: {d.get('filename','')[:50]}"

    ydl_opts['progress_hooks'].append(progress_hook)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for url in urls:
            try:
                ydl.download([url])
            except Exception as e:
                errors.append(str(e))

    zip_path = download_dir.parent / f"youtube_{download_id}.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for f in os.listdir(download_dir):
            full = os.path.join(download_dir, f)
            if os.path.isfile(full):
                zipf.write(full, f)

    with downloads_lock:
        downloads[download_id]['status'] = 'completed'
        downloads[download_id]['progress'] = 100
        downloads[download_id]['zip_path'] = str(zip_path)
        downloads[download_id]['current'] = f"Completed! {completed}/{total} downloaded"
        downloads[download_id]['errors'] = errors

# ---------------- HTML Template ----------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>YouTube Downloader</title>
<style>
body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana; background: #f7f9fc; padding: 20px; }
h2 { text-align:center; color: #333; }
.container { max-width: 800px; margin: auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);}
textarea { width: 100%; height: 100px; padding: 10px; border-radius: 8px; border: 1px solid #ccc; margin-bottom: 15px; resize:none;}
select, button { width: 100%; padding: 12px; margin: 10px 0; border-radius: 8px; border: 1px solid #667eea; font-size:16px;}
button { background: #667eea; color:white; cursor:pointer; transition: 0.3s;}
button:hover { background: #556cd6; }
.progress-bar { background:#e0e0e0; width:100%; height:28px; border-radius:14px; overflow:hidden; margin-top:10px;}
.progress-fill { background:#667eea; height:100%; width:0%; text-align:center; color:white; font-weight:bold; line-height:28px;}
.error-message { color:red; margin-top:5px; font-size:14px;}
.download-link { display:inline-block; background:#28a745; color:white; padding:8px 20px; border-radius:5px; text-decoration:none; margin-top:10px; font-weight:bold; transition:0.3s;}
.download-link:hover { background:#218838; }
.download-item { margin-bottom: 25px; border-bottom:1px solid #ddd; padding-bottom:10px;}
</style>
</head>
<body>
<div class="container">
<h2>YouTube Downloader</h2>
<textarea id="urls" placeholder="Enter URLs (comma-separated or playlist URL)"></textarea>
<select id="quality">
<option value="360">360p</option>
<option value="480">480p</option>
<option value="720" selected>720p</option>
<option value="1080">1080p</option>
<option value="best">Best</option>
</select>
<button id="downloadBtn">📥 Start Download</button>

<div id="downloads"></div>
</div>


<script>
function createUI(downloadId) {
    const container = document.getElementById('downloads');
    const div = document.createElement('div');
    div.className = 'download-item';
    div.id = 'download-' + downloadId;
    div.innerHTML = `
        <div class="progress-bar"><div class="progress-fill" id="fill-${downloadId}">0%</div></div>
        <div class="status" id="status-${downloadId}">Starting...</div>
        <div class="errors" id="errors-${downloadId}"></div>
        <div id="link-${downloadId}"></div>
    `;
    container.prepend(div);
}

function updateUI(downloadId, data) {
    document.getElementById('fill-' + downloadId).style.width = data.progress + '%';
    document.getElementById('fill-' + downloadId).textContent = data.progress + '%';
    document.getElementById('status-' + downloadId).textContent = data.current || '';
    if(data.errors && data.errors.length>0){
        document.getElementById('errors-' + downloadId).innerHTML = data.errors.map(e=>'<div class="error-message">'+e+'</div>').join('');
    }
    if(data.status==='completed'){
        document.getElementById('link-' + downloadId).innerHTML = '<a class="download-link" href="/download_zip/'+downloadId+'">📦 Download All Videos as Zip</a>';
    }
}

async function poll(downloadId){
    try{
        const res = await fetch('/progress/'+downloadId);
        const data = await res.json();
        updateUI(downloadId,data);
        if(data.status!=='completed') setTimeout(()=>poll(downloadId),1500);
    }catch{ setTimeout(()=>poll(downloadId),5000); }
}

document.getElementById('downloadBtn').addEventListener('click', async ()=>{
    const urls = document.getElementById('urls').value.split(',').map(u=>u.trim()).filter(u=>u);
    const quality = document.getElementById('quality').value;
    if(!urls.length){ alert('Enter URLs'); return; }

    const res = await fetch('/download', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({urls,quality})
    });
    const data = await res.json();
    if(!data.success){ alert(data.error || 'Error'); return; }
    createUI(data.download_id);
    poll(data.download_id);
});
</script>
</body>
</html>
"""

# ---------------- Flask Routes ----------------
@app.route('/')
def index():
    return HTML_TEMPLATE

@app.route('/download', methods=['POST'])
def start_download():
    data = request.json
    urls = data.get('urls', [])
    quality = data.get('quality','720')
    valid_urls = [u for u in urls if is_valid_youtube_url(u)]
    if not valid_urls: return jsonify({'success':False,'error':'No valid URLs'})
    download_id = str(uuid.uuid4())[:8]
    with downloads_lock:
        downloads[download_id] = {'status':'starting','progress':0,'current':'Initializing','errors':[],'timestamp':time.time()}
    threading.Thread(target=download_videos,args=(valid_urls,download_id,None,quality),daemon=True).start()
    return jsonify({'success':True,'download_id':download_id})

@app.route('/progress/<download_id>')
def progress(download_id):
    with downloads_lock:
        if download_id not in downloads: return jsonify({'error':'Not found'}),404
        return jsonify(downloads[download_id])

@app.route('/download_zip/<download_id>')
def download_zip(download_id):
    with downloads_lock:
        if download_id not in downloads: return "Not found",404
        info = downloads[download_id]
    if info['status']!='completed': return f"Status: {info['status']}",400
    zip_path = info.get('zip_path')
    if not zip_path or not os.path.exists(zip_path): return "Zip not found",404
    return send_file(zip_path, as_attachment=True, download_name=f'youtube_{download_id}.zip', mimetype='application/zip')

# ---------------- Run App ----------------
if __name__=="__main__":
    if not install_yt_dlp(): sys.exit(1)
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
