import os
import socket
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import pyperclip
import qrcode

from discovery import UDPDiscoveryEngine
# IMPORT THE NEW CHUNKED TRANSFER ENGINE
from transfer_engine import TesseraTransferEngine

app = Flask(__name__, 
            template_folder='../templates', 
            static_folder='../static')

DROP_ZONE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../storage'))
app.config['UPLOAD_FOLDER'] = DROP_ZONE
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

os.makedirs(DROP_ZONE, exist_ok=True)

discovery_node = None
# Instantiate Global Variable pointer for our TCP stream service
transfer_node = None

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
    
    # Force printing with standard text characters instead of broken ANSI blocks
    qr.print_ascii(invert=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/clipboard', methods=['POST'])
def update_clipboard():
    data = request.get_json()
    if not data or 'content' not in data:
        return jsonify({'error': 'No text block content detected'}), 400
    try:
        pyperclip.copy(data['content'])
        print(f"\n📋 [Clipboard] Sync received from node: {request.remote_addr}")
        return jsonify({'status': 'success', 'message': 'Tessera Host Clipboard Updated!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file element detected in packet stream'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty target filename string'}), 400
    if file:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        print(f"\n📥 [File Drop] Successfully saved file '{filename}' from address {request.remote_addr}")
        return jsonify({'status': 'success', 'message': f"Stored context as {filename}"})

@app.route('/api/peers', methods=['GET'])
def get_discovered_peers():
    if discovery_node:
        return jsonify(discovery_node.get_active_peers())
    return jsonify({})

# NEW OUTBOUND TRIGGER ENDPOINT: Tells this PC to send a file to another PC via raw TCP sockets
@app.route('/api/send_peer', methods=['POST'])
def send_file_to_peer():
    data = request.get_json()
    if not data or 'target_ip' not in data or 'file_path' not in data:
        return jsonify({'error': 'Missing parameters target_ip or file_path'}), 400
    
    if transfer_node:
        success = transfer_node.send_file(data['target_ip'], data['file_path'])
        if success:
            return jsonify({'status': 'success', 'message': f"Outbound stream initiated for {data['file_path']}"})
        return jsonify({'error': 'File initialization engine error'}), 500
    return jsonify({'error': 'Transfer backend node offline'}), 500

if __name__ == '__main__':
    local_ip = get_local_ip()
    hostname = socket.gethostname()
    port = 5000
    server_url = f"http://{local_ip}:{port}"
    
    # Initialize UDP discovery engines
    discovery_node = UDPDiscoveryEngine(local_ip=local_ip, hostname=hostname)
    discovery_node.start_broadcaster()
    discovery_node.start_listener()
    
    # Fire up the parallel high-speed TCP Socket stream layer
    transfer_node = TesseraTransferEngine(local_ip=local_ip)
    transfer_node.start_receiver_server()
    
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