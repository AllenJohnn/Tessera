import os
import socket
import time
import threading
import random
import uuid
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

# Helper to fetch local IP address
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

LOCAL_IP = get_local_ip()

# Node engine integrations
from discovery import UDPDiscoveryEngine
from transfer_engine import TesseraTransferEngine
from sync_watcher import start_folder_sync_watcher

SERVER_HOSTNAME = f"{random.choice(BRUTALIST_PREFIXES)}_{random.randint(100, 999)}"

discovery_node = UDPDiscoveryEngine(LOCAL_IP, SERVER_HOSTNAME)
discovery_node.start_broadcaster()
discovery_node.start_listener()

transfer_node = TesseraTransferEngine(LOCAL_IP)
transfer_node.start_receiver_server()

try:
    sync_observer = start_folder_sync_watcher(LOCAL_IP)
except Exception as e:
    print(f"⚠️ [Sync Watcher Warning] Failed to start folder watch: {e}")
    sync_observer = None

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
        
    device_id = data.get("device_id")
    if device_id:
        device_id = "".join(c for c in str(device_id) if c.isalnum() or c in '-_')[:50]
        
    if not device_id:
        device_id = str(uuid.uuid4())
        
    if not assigned_hostname:
        if device_id in HTTP_ACTIVE_DEVICES:
            assigned_hostname = HTTP_ACTIVE_DEVICES[device_id]["hostname"]
        else:
            assigned_hostname = f"{random.choice(BRUTALIST_PREFIXES)}_{random.randint(100, 999)}"
    
    device_type = "Mobile Device" if "iphone" in user_agent or "android" in user_agent else "Web Workstation"
    HTTP_ACTIVE_DEVICES[device_id] = {
        "hostname": assigned_hostname,
        "type": device_type,
        "last_seen": time.time(),
        "ip": client_ip
    }
    
    return jsonify({
        "status": "acknowledged", 
        "assigned_name": assigned_hostname,
        "device_id": device_id,
        "active_nodes": [{"name": dev["hostname"], "type": dev["type"]} for dev in HTTP_ACTIVE_DEVICES.values() if time.time() - dev["last_seen"] < 12]
    })

@app.route('/api/peers', methods=['GET'])
def get_discovered_peers():
    now = time.time()
    unified_devices = {}
    
    # 1. Get HTTP active devices
    for dev_id, data in list(HTTP_ACTIVE_DEVICES.items()):
        if now - data["last_seen"] < 12:
            unified_devices[dev_id] = {
                "hostname": data["hostname"],
                "type": data["type"],
                "last_seen": data["last_seen"],
                "ip": data["ip"]
            }
        else:
            HTTP_ACTIVE_DEVICES.pop(dev_id, None)
            
    # 2. Add local network peers discovered via UDP broadcast
    if discovery_node:
        udp_peers = discovery_node.get_active_peers()
        for peer_ip, data in udp_peers.items():
            peer_dev_id = f"udp_{peer_ip.replace('.', '_')}"
            if peer_dev_id not in unified_devices:
                unified_devices[peer_dev_id] = {
                    "hostname": data["hostname"],
                    "type": "Network Workstation",
                    "last_seen": now,
                    "ip": peer_ip
                }
                
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
    
    device_id = data.get('device_id')
    sender_name = "EXTERNAL_NODE"
    if device_id and device_id in HTTP_ACTIVE_DEVICES:
        sender_name = HTTP_ACTIVE_DEVICES[device_id].get('hostname', "EXTERNAL_NODE")
    else:
        # Fallback to checking by IP
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
        for dev in HTTP_ACTIVE_DEVICES.values():
            if dev.get('ip') == client_ip:
                sender_name = dev.get('hostname', "EXTERNAL_NODE")
                break
                
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
        device_id = request.form.get('device_id')
        sender_name = "NODE"
        if device_id and device_id in HTTP_ACTIVE_DEVICES:
            sender_name = HTTP_ACTIVE_DEVICES[device_id].get('hostname', "NODE")
        else:
            # Fallback to checking by IP
            client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
            for dev in HTTP_ACTIVE_DEVICES.values():
                if dev.get('ip') == client_ip:
                    sender_name = dev.get('hostname', "NODE")
                    break
                    
        sender_name = sender_name.replace(" ", "_").upper()
        
        # SECURITY ENHANCEMENT: Enforce path sanitation scrubbing to block traversal exploits
        raw_filename = secure_filename(file.filename)
        stamped_filename = f"{sender_name}_{raw_filename}"
        
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], stamped_filename))
        return jsonify({'status': 'success'})

@app.route('/api/send_peer', methods=['POST'])
def send_file_to_peer():
    if 'file' not in request.files: return jsonify({'error': 'No element'}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({'error': 'Empty parameters'}), 400
    
    # SECURITY ENHANCEMENT: Enforce extension constraints validation check
    if not allowed_file(file.filename):
        return jsonify({'error': 'Execution blocked: File extension type unauthorized.'}), 403
        
    target_peer = request.form.get('target_peer')
    if not target_peer:
        return jsonify({'error': 'No target peer specified'}), 400
        
    # Resolve target IP
    target_ip = None
    if target_peer.startswith("udp_"):
        raw_ip = target_peer[4:].replace("_", ".")
        try:
            socket.inet_aton(raw_ip)
            target_ip = raw_ip
        except socket.error:
            pass
    else:
        if target_peer in HTTP_ACTIVE_DEVICES:
            target_ip = HTTP_ACTIVE_DEVICES[target_peer].get("ip")
            
    if not target_ip:
        try:
            socket.inet_aton(target_peer)
            target_ip = target_peer
        except socket.error:
            return jsonify({'error': f'Could not resolve peer IP: {target_peer}'}), 400
            
    # Save file locally in a temp folder first to preserve the original filename
    raw_filename = secure_filename(file.filename)
    temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], f"temp_{int(time.time())}")
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, raw_filename)
    file.save(temp_path)
    
    def async_send():
        try:
            success = transfer_node.send_file(target_ip, temp_path)
            if success:
                print(f"[Async Send] File transfer to {target_ip} completed.")
            else:
                print(f"[Async Send] File transfer to {target_ip} failed.")
        except Exception as e:
            print(f"[Async Send] Exception in async file transfer: {e}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            try:
                os.rmdir(temp_dir)
            except Exception:
                pass
                
    threading.Thread(target=async_send, daemon=True).start()
    return jsonify({'status': 'success', 'message': f'File transfer to {target_ip} initiated.'})

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