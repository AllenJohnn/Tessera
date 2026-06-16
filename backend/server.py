import os
import socket
import time
import threading
import random
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import pyperclip
import qrcode

from discovery import UDPDiscoveryEngine
from transfer_engine import TesseraTransferEngine
from sync_watcher import start_folder_sync_watcher
from state_store import TesseraStateStore

# Dynamic absolute directory paths for cloud-hosting execution stability
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATE_DIR = os.path.abspath(os.path.join(BASE_DIR, '../templates'))
STATIC_DIR = os.path.abspath(os.path.join(BASE_DIR, '../static'))
DROP_ZONE = os.path.abspath(os.path.join(BASE_DIR, '../storage'))

app = Flask(__name__, 
            template_folder=TEMPLATE_DIR, 
            static_folder=STATIC_DIR)

app.config['UPLOAD_FOLDER'] = DROP_ZONE
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

os.makedirs(DROP_ZONE, exist_ok=True)

discovery_node = None
transfer_node = None
sync_observer = None
db_store = None 

# Dynamic registry tracking web/mobile sessions
HTTP_ACTIVE_DEVICES = {}

# Central memory cache for headless environment clips
WEB_CLIPBOARD_CACHE = {"content": "", "sender": "SYSTEM", "timestamp": 0}

# Curated prefix list for generating frictionless, brutalist fallbacks
BRUTALIST_PREFIXES = ["CORE", "NODE", "SATELLITE", "PHANTOM", "MATRIX", "VECTOR", "ALPHA", "SPECTRE"]

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = '127.0.0.1'
    finally:
        s.close()
    return local_ip

def generate_terminal_qr(url):
    qr = qrcode.QRCode(version=1, box_size=1, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)

@app.route('/')
def index():
    cache_buster = str(int(time.time()))
    return render_template('index.html', version=cache_buster)

@app.route('/api/ping', methods=['POST'])
def register_device_ping():
    data = request.get_json() or {}
    user_agent = request.headers.get('User-Agent', '').lower()
    
    # Extract the true external client IP behind the cloud proxy layer
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    
    # FIXED: Check if the client already has a known identity, or generate a zero-friction fallback
    assigned_hostname = data.get("hostname")
    if not assigned_hostname:
        # Check if we already assigned them a name previously to avoid rapid cycling
        if client_ip in HTTP_ACTIVE_DEVICES:
            assigned_hostname = HTTP_ACTIVE_DEVICES[client_ip]["hostname"]
        else:
            random_id = random.randint(100, 999)
            random_prefix = random.choice(BRUTALIST_PREFIXES)
            assigned_hostname = f"{random_prefix}-{random_id}"
    
    if "iphone" in user_agent or "android" in user_agent:
        device_type = "Mobile Device"
    elif "ipad" in user_agent:
        device_type = "Tablet Client"
    else:
        device_type = "Web Workstation"
        
    HTTP_ACTIVE_DEVICES[client_ip] = {
        "hostname": assigned_hostname,
        "type": device_type,
        "last_seen": time.time()
    }
    
    # Return the callsign back to frontend so it can synchronize local memory stores
    return jsonify({"status": "acknowledged", "assigned_name": assigned_hostname})

@app.route('/api/peers', methods=['GET'])
def get_discovered_peers():
    now = time.time()
    unified_devices = {}
    
    if discovery_node:
        for ip, data in discovery_node.get_active_peers().items():
            unified_devices[ip] = {
                "hostname": data.get("hostname", "Unknown PC"),
                "type": "Desktop Core Node"
            }
            
    for ip, data in list(HTTP_ACTIVE_DEVICES.items()):
        if now - data["last_seen"] < 12:
            if ip not in unified_devices:
                unified_devices[ip] = {
                    "hostname": data["hostname"],
                    "type": data["type"]
                }
        else:
            HTTP_ACTIVE_DEVICES.pop(ip, None)
            
    return jsonify(unified_devices)

@app.route('/api/clipboard', methods=['POST'])
def update_clipboard():
    global WEB_CLIPBOARD_CACHE
    data = request.get_json()
    if not data or 'content' not in data:
        return jsonify({'error': 'No text content detected'}), 400
        
    text_content = data['content']
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    
    # FIXED: Extract sender identity from live tracking registry maps
    device_info = HTTP_ACTIVE_DEVICES.get(client_ip, {})
    sender_name = device_info.get('hostname', f"NODE [{client_ip.split('.')[-1]}]")
    
    # Pack the payload bundled explicitly with its creator signature tag
    WEB_CLIPBOARD_CACHE = {
        "content": text_content,
        "sender": sender_name,
        "timestamp": time.time()
    }
    
    try:
        pyperclip.copy(text_content)
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text_content, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
        except ImportError:
            pass
        print(f"\n📋 [Clipboard] Direct hardware sync completed from node: {sender_name}")
    except Exception:
        print(f"\n☁️ [Cloud Clipboard] Text cached successfully from: {sender_name}")

    return jsonify({'status': 'success', 'message': 'Clipboard Updated!'})

@app.route('/api/clipboard/get', methods=['GET'])
def get_cached_clipboard():
    """Allows client instances to pull the latest text block from memory."""
    global WEB_CLIPBOARD_CACHE
    return jsonify(WEB_CLIPBOARD_CACHE)

@app.route('/api/send_peer', methods=['POST'])
def send_file_to_peer():
    """Handles routing files to active desktop nodes or fallback cloud pools."""
    global transfer_node
    data = request.get_json() or {}
    target_ip = data.get("target_ip")
    filename = data.get("file_path")
    
    if not target_ip or not filename:
        return jsonify({"status": "error", "message": "Missing arguments"}), 400
        
    actual_file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    if target_ip in HTTP_ACTIVE_DEVICES:
        print(f"ℹ️ [Routing Switch] Target {target_ip} is a browser client. Kept in local web storage.")
        return jsonify({"status": "success", "message": "File prepared in cloud file ledger."})

    if transfer_node and os.path.exists(actual_file_path):
        threading.Thread(
            target=transfer_node.send_file, 
            args=(target_ip, actual_file_path), 
            daemon=True
        ).start()
        return jsonify({"status": "success", "message": "Socket stream sequence started"})
        
    return jsonify({"status": "error", "message": "File missing from host system"}), 404

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file element detected'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty file parameters'}), 400
        
    if file:
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
        device_info = HTTP_ACTIVE_DEVICES.get(client_ip, {})
        sender_name = device_info.get('hostname', f"NODE-{client_ip.split('.')[-1]}").replace(" ", "_").upper()
        
        # FIXED: Append structural sender initials onto file descriptors to clear multi-device overlap
        raw_filename = secure_filename(file.filename)
        stamped_filename = f"{sender_name}_{raw_filename}"
        
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], stamped_filename))
        
        if db_store:
            db_store.log_transfer(stamped_filename, 1, 'completed', client_ip)
            
        print(f"\n📥 [File Drop] Saved file '{stamped_filename}' from address {client_ip}")
        return jsonify({'status': 'success', 'message': f"Stored context as {stamped_filename}"})

@app.route('/api/files', methods=['GET'])
def list_stored_files():
    try:
        files = os.listdir(app.config['UPLOAD_FOLDER'])
        file_data = []
        for f in files:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f)
            if os.path.isfile(file_path):
                file_data.append({
                    "name": f,
                    "size": f"{round(os.path.getsize(file_path) / (1024*1024), 2)} MB"
                })
        return jsonify(file_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/clear_files', methods=['POST'])
def clear_stored_files():
    try:
        files = os.listdir(app.config['UPLOAD_FOLDER'])
        for f in files:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f)
            if os.path.isfile(file_path):
                os.remove(file_path)
        print(f"\n🗑️ [Storage Purge] Directory wiped clear by request.")
        return jsonify({"status": "success", "message": "Storage purged"})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/storage/<filename>', methods=['GET'])
def download_file_direct(filename):
    from flask import send_from_directory
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    local_ip = get_local_ip()
    hostname = socket.gethostname()
    port = 5000
    server_url = f"http://{local_ip}:{port}"
    
    db_store = TesseraStateStore()
    
    discovery_node = UDPDiscoveryEngine(local_ip=local_ip, hostname=hostname)
    discovery_node.start_broadcaster()
    discovery_node.start_listener()
    
    transfer_node = TesseraTransferEngine(local_ip=local_ip)
    transfer_node.start_receiver_server()
    
    sync_observer = start_folder_sync_watcher(local_ip=local_ip)
    
    print("\n" + "═"*50)
    print(f" 🌟 TESSERA INTERFACE HOST: ACTIVE 🌟 ")
    print("═"*50)
    print(f"Node Name: {hostname}")
    print(f"Local IP Address Pointer: {local_ip}")
    print(f"Scan this target block to access Tessera from mobile:")
    generate_terminal_qr(server_url)
    print(f"\nLocal URI string pointer: {server_url}")
    print("═"*50 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)