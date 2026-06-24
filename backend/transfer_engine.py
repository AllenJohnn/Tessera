import os
import socket
import json
import threading
from werkzeug.utils import secure_filename

class TesseraTransferEngine:
    def __init__(self, local_ip, port=6000, storage_dir='../storage'):
        self.local_ip = local_ip
        self.port = port
        self.storage_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), storage_dir))
        self.chunk_size = 512 * 1024  # 512 KB sequential blocks
        os.makedirs(self.storage_dir, exist_ok=True)

    def start_receiver_server(self):
        """Spins up a permanent, non-blocking TCP daemon thread to catch files."""
        server_thread = threading.Thread(target=self._run_receiver_loop, daemon=True)
        server_thread.start()
        print(f"[Transfer Engine] TCP Receiver Server listening on port {self.port}.")

    def _run_receiver_loop(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(('0.0.0.0', self.port))
        server_sock.listen(5)

        while True:
            try:
                client_sock, client_addr = server_sock.accept()
                handler = threading.Thread(target=self._handle_incoming_stream, args=(client_sock, client_addr))
                handler.start()
            except Exception as e:
                print(f"[TCP Server Error] Connection dropped: {e}")

    def _handle_incoming_stream(self, sock, addr):
        """Processes the Tessera packet frame and manages chunk accumulation."""
        try:
            # 1. Read the fixed 512-byte metadata header frame
            header_bytes = sock.recv(512)
            if not header_bytes:
                return
            
            header_data = json.loads(header_bytes.decode('utf-8').strip())
            filename = header_data['filename']
            total_size = header_data['total_size']
            
            # SECURITY ENHANCEMENT: Sanitize filename to block path traversal write exploits
            clean_filename = secure_filename(filename)
            
            # SECURITY ENHANCEMENT: Whitelist validation check to prevent arbitrary execution files
            ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'rar', 'mp4', 'mp3', 'json', 'apk'}
            ext = clean_filename.rsplit('.', 1)[1].lower() if '.' in clean_filename else ''
            if ext not in ALLOWED_EXTENSIONS:
                print(f"[TCP Receiver Error] Blocked unauthorized file type: {clean_filename}")
                return
                
            final_path = os.path.join(self.storage_dir, clean_filename)
            part_path = final_path + ".part"

            # 2. Handshake Phase: Send current write-offset back to sender
            current_offset = os.path.getsize(part_path) if os.path.exists(part_path) else 0
            sock.sendall(str(current_offset).encode('utf-8').zfill(32))

            # 3. Stream Accumulation Phase
            with open(part_path, 'ab' if current_offset > 0 else 'wb') as f:
                if current_offset > 0:
                    f.seek(current_offset)
                
                print(f"[TCP Receiver] Ingesting '{filename}' from {addr[0]} starting at byte {current_offset}")
                
                while True:
                    data = sock.recv(self.chunk_size)
                    if not data:
                        break
                    f.write(data)

            # 4. Finalize file structure if verification balances out
            if os.path.getsize(part_path) >= total_size:
                if os.path.exists(final_path):
                    os.remove(final_path)
                os.rename(part_path, final_path)
                print(f"[TCP Stream Finalized] Verified and stored: {filename}")
                
        except Exception as e:
            print(f"[TCP Receive Fault] Stream pipeline crash: {e}")
        finally:
            sock.close()

    def send_file(self, target_ip, file_path):
        """Initiates a high-throughput TCP connection to a peer workstation node."""
        if not os.path.exists(file_path):
            print(f"[TCP Sender Error] Source file missing: {file_path}")
            return False

        try:
            filename = os.path.basename(file_path)
            total_size = os.path.getsize(file_path)

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((target_ip, self.port))

            # 1. Build and push the exact 512-byte structural header block
            header = {"filename": filename, "total_size": total_size}
            header_bytes = json.dumps(header).encode('utf-8')
            header_bytes = header_bytes.ljust(512)  # Pad out to exact static frame size
            sock.sendall(header_bytes)

            # 2. Handshake Phase: Collect target write offset token
            offset_response = sock.recv(32).decode('utf-8').strip()
            start_offset = int(offset_response) if offset_response else 0

            # 3. Chunked Streaming Phase
            print(f"[TCP Sender] Streaming '{filename}' to {target_ip} from byte offset {start_offset}")
            with open(file_path, 'rb') as f:
                f.seek(start_offset)
                while True:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    sock.sendall(chunk)

            sock.close()
            return True
        except Exception as e:
            print(f"[TCP Send Fault] Failed to stream to remote target {target_ip}: {e}")
            return False