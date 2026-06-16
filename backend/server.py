import os
import socket
import time
import threading
import random
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

# Dynamic absolute directory paths for cloud-hosting execution stability
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATE_DIR = os.path.abspath(os.path.join(BASE_DIR, '../templates'))
STATIC_DIR = os.path.abspath(os.path.join(BASE_DIR, '../static'))
DROP_ZONE = os.path.abspath(os.path.join(BASE_DIR, '../storage'))

app = Flask(__name__, 
            template_folder=TEMPLATE_DIR, 
            static_folder=STATIC_DIR)

app.config['UPLOAD_FOLDER'] = DROP_ZONE
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # Capped at 100MB to prevent cloud memory exhaustion crashes

os.makedirs(DROP_ZONE, exist_ok=True)

# SECURITY ENHANCEMENT: Restrict execution surface by whitelisting safe media/doc types
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'rar', 'mp4', 'mp3', 'json', 'apk'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

HTTP_ACTIVE_DEVICES = {}

WEB_CLIPBOARD_SLOTS = {
    "SLOT_01": {"content": "", "sender": "SYSTEM", "timestamp": 0},
    "SLOT_02": {"content": "", "sender": "SYSTEM", "timestamp": 0},
    "SLOT_03": {"content": "", "sender": "SYSTEM", "timestamp": 0}
}

BRUTALIST_PREFIXES = ["CORE", "NODE", "SATELLITE", "PHANTOM", "MATRIX", "VECTOR", "ALPHA", "SPECTRE"]

def run_storage_lifecycle_guard():
    while True:
        try:
            now = time.time()
            if os.path.exists(DROP_ZONE):
                for f in os.listdir(DROP_ZONE):
                    file_path = os.path.join(DROP_ZONE, f)
                    if os.path.isfile(file_path):
                        if (now - os.path.getmtime(file_path)) > 1800:
                            os.remove(file_path)
                            print(f"🗑️ [Memory Guard] Auto-purged: {f}")
        except Exception as e:
            print(f"❌ [Guard Error]: {e}")
        time.sleep(60)

threading.Thread(target=run_storage_lifecycle_guard, daemon=True).start()

@app.route('/')
def index():
    return render_template('index.html', version=str(int(time.time())))

@app.route('/api/ping', methods=['POST'])
def register_device_ping():
    data = request.get_json() or {}
    user_agent = request.headers.get('User-Agent', '').lower()
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    
    assigned_hostname = data.get("hostname")
    if assigned_hostname:
        # SECURITY ENHANCEMENT: Sanitize the callsign to prevent header/UI manipulation strings
        assigned_hostname = "".join(c for c in str(assigned_hostname) if c.isalnum() or c in '-_')[:15]
        
    if not assigned_hostname:
        if client_ip in HTTP_ACTIVE_DEVICES:
            assigned_hostname = HTTP_ACTIVE_DEVICES[client_ip]["hostname"]
        else:
            assigned_hostname = f"{random.choice(BRUTALIST_PREFIXES)}_{random.randint(100, 999)}"
    
    device_type = "Mobile Device" if "iphone" in user_agent or "android" in user_agent else "Web Workstation"
    HTTP_ACTIVE_DEVICES[client_ip] = {"hostname": assigned_hostname, "type": device_type, "last_seen": time.time()}
    
    return jsonify({
        "status": "acknowledged", 
        "assigned_name": assigned_hostname,
        "active_nodes": [{"name": dev["hostname"], "type": dev["type"]} for dev in HTTP_ACTIVE_DEVICES.values() if time.time() - dev["last_seen"] < 12]
    })

@app.route('/api/peers', methods=['GET'])
def get_discovered_peers():
    now = time.time()
    unified_devices = {}
    for ip, data in list(HTTP_ACTIVE_DEVICES.items()):
        if now - data["last_seen"] < 12:
            unified_devices[ip] = {"hostname": data["hostname"], "type": data["type"], "last_seen": data["last_seen"]}
        else:
            HTTP_ACTIVE_DEVICES.pop(ip, None)
    return jsonify(unified_devices)

@app.route('/api/clipboard', methods=['POST'])
def update_clipboard():
    data = request.get_json()
    if not data or 'content' not in data:
        return jsonify({'error': 'No content'}), 400
        
    slot = data.get('slot', 'SLOT_01')
    if slot not in WEB_CLIPBOARD_SLOTS: slot = 'SLOT_01'

    # SECURITY ENHANCEMENT: Cap text data packets at 50,000 characters to block buffer overflow spam
    text_content = str(data['content'])[:50000]
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    sender_name = HTTP_ACTIVE_DEVICES.get(client_ip, {}).get('hostname', "EXTERNAL_NODE")
    
    WEB_CLIPBOARD_SLOTS[slot] = {"content": text_content, "sender": sender_name, "timestamp": time.time()}
    return jsonify({'status': 'success', 'message': f'Channel {slot} synchronized.'})

@app.route('/api/clipboard/get', methods=['GET'])
def get_cached_clipboard():
    slot = request.args.get('slot', 'SLOT_01')
    if slot not in WEB_CLIPBOARD_SLOTS: slot = 'SLOT_01'
    return jsonify(WEB_CLIPBOARD_SLOTS[slot])

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({'error': 'No element'}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({'error': 'Empty parameters'}), 400
    
    # SECURITY ENHANCEMENT: Enforce extension constraints validation check
    if not allowed_file(file.filename):
        return jsonify({'error': 'Execution blocked: File extension type unauthorized.'}), 403
        
    if file:
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
        sender_name = HTTP_ACTIVE_DEVICES.get(client_ip, {}).get('hostname', "NODE").replace(" ", "_").upper()
        
        # SECURITY ENHANCEMENT: Enforce path sanitation scrubbing to block traversal exploits
        raw_filename = secure_filename(file.filename)
        stamped_filename = f"{sender_name}_{raw_filename}"
        
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], stamped_filename))
        return jsonify({'status': 'success'})

@app.route('/api/files', methods=['GET'])
def list_stored_files():
    try:
        files = os.listdir(app.config['UPLOAD_FOLDER'])
        file_data = []
        now = time.time()
        for f in files:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f)
            if os.path.isfile(file_path):
                elapsed = now - os.path.getmtime(file_path)
                remaining_min = max(0, int((1800 - elapsed) / 60))
                file_data.append({
                    "name": f, "size": f"{round(os.path.getsize(file_path) / (1024*1024), 2)} MB", "ttl": f"EXPIRING IN {remaining_min}M"
                })
        return jsonify(file_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/clear_files', methods=['POST'])
def clear_stored_files():
    try:
        for f in os.listdir(app.config['UPLOAD_FOLDER']):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f)
            if os.path.isfile(file_path): os.remove(file_path)
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/storage/<filename>', methods=['GET'])
def download_file_direct(filename):
    # SECURITY ENHANCEMENT: Force path compilation targeting inside send_from_directory boundaries
    from flask import send_from_directory
    clean_filename = secure_filename(filename)
    return send_from_directory(app.config['UPLOAD_FOLDER'], clean_filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)