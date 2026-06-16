import os
import socket
import time
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import pyperclip
import qrcode

from discovery import UDPDiscoveryEngine
from transfer_engine import TesseraTransferEngine
from sync_watcher import start_folder_sync_watcher
from state_store import TesseraStateStore

app = Flask(__name__, 
            template_folder='../templates', 
            static_folder='../static')

DROP_ZONE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../storage'))
app.config['UPLOAD_FOLDER'] = DROP_ZONE
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

os.makedirs(DROP_ZONE, exist_ok=True)

discovery_node = None
transfer_node = None
sync_observer = None
db_store = None 

# Dynamic registry tracking mobile client pings
HTTP_ACTIVE_DEVICES = {}

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
    
    if "iphone" in user_agent or "android" in user_agent:
        device_type = "Mobile Device"
    elif "ipad" in user_agent:
        device_type = "Tablet Client"
    else:
        device_type = "Web Workstation"
        
    client_ip = request.remote_addr
    
    HTTP_ACTIVE_DEVICES[client_ip] = {
        "hostname": data.get("hostname", f"Satellite [{client_ip.split('.')[-1]}]"),
        "type": device_type,
        "last_seen": time.time()
    }
    return jsonify({"status": "acknowledged"})

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
    data = request.get_json()
    if not data or 'content' not in data:
        return jsonify({'error': 'No text content detected'}), 400
    try:
        text_content = data['content']
        pyperclip.copy(text_content)
        
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text_content, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
        except ImportError:
            pass 
            
        print(f"\n📋 [Clipboard] Sync received from node: {request.remote_addr}")
        return jsonify({'status': 'success', 'message': 'Tessera Host Clipboard Updated!'})
    except Exception as e:
        print(f"\n❌ [Clipboard Error] Native API write lock violation: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file element detected in packet stream'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty file parameters'}), 400
    if file:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        if db_store:
            db_store.log_transfer(filename, 1, 'completed', request.remote_addr)
            
        print(f"\n📥 [File Drop] Saved file '{filename}' from address {request.remote_addr}")
        return jsonify({'status': 'success', 'message': f"Stored context as {filename}"})

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

# FIXED & ADDED: Storage directory cleaner router endpoint mapping
@app.route('/api/clear_files', methods=['POST'])
def clear_stored_files():
    """Wipes all files inside the local storage directory cleanly."""
    try:
        files = os.listdir(app.config['UPLOAD_FOLDER'])
        for f in files:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f)
            if os.path.isfile(file_path):
                os.remove(file_path)
        print(f"\n🗑️ [Storage Purge] Directory wiped clear by request from: {request.remote_addr}")
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