import socket
import os
import json
import threading

class TesseraTransferEngine:
    def __init__(self, local_ip):
        self.local_ip = local_ip
        self.port = 6000                     # Core TCP data socket port
        self.chunk_size = 524288              # Fixed 512KB chunks (512 * 1024 bytes)
        self.storage_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../storage'))
        self.state_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../.landrop_state'))
        
        self.running = False
        os.makedirs(self.storage_dir, exist_ok=True)
        os.makedirs(self.state_dir, exist_ok=True)

    def start_receiver_server(self):
        """Spins up a background TCP server to listen for incoming file streams."""
        self.running = True
        server_thread = threading.Thread(target=self._server_loop, daemon=True)
        server_thread.start()
        print(f"[Transfer Engine] TCP Receiver Server listening on port {self.port}.")

    def _server_loop(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(('0.0.0.0', self.port))
        server_sock.listen(5)
        
        while self.running:
            try:
                client_sock, addr = server_sock.accept()
                client_thread = threading.Thread(
                    target=self._handle_incoming_file, 
                    args=(client_sock, addr), 
                    daemon=True
                )
                client_thread.start()
            except Exception as e:
                if self.running:
                    print(f"[Transfer Error] Receiver accept loop crashed: {e}")
        server_sock.close()

    def _get_sidecar_paths(self, filename):
        """Generates predictable tracking paths for partial data and state sidecars."""
        safe_filename = "".join([c for c in filename if c.isalpha() or c.isdigit() or c in ('.','_','-')]).strip()
        partial_path = os.path.join(self.storage_dir, f"{safe_filename}.landrop_partial")
        sidecar_path = os.path.join(self.state_dir, f"{safe_filename}.transfer_state.json")
        return partial_path, sidecar_path

    def _handle_incoming_file(self, client_sock, addr):
        """Receiver Engine: Performs resume handshakes and manages chunked state persistence."""
        print(f"\n📥 [TCP Inbound] Target node connection from: {addr[0]}")
        try:
            # 1. Capture the structural metadata header configuration
            header = client_sock.recv(1024).decode('utf-8').strip()
            if not header:
                return
                
            filename, file_size_str = header.split('|')
            file_size = int(file_size_str)
            
            partial_path, sidecar_path = self._get_sidecar_paths(filename)
            
            # 2. Handshake Phase: Verify if a partial file sidecar already exists on disk
            confirmed_chunks = 0
            if os.path.exists(sidecar_path) and os.path.exists(partial_path):
                try:
                    with open(sidecar_path, 'r') as sf:
                        state_data = json.load(sf)
                        confirmed_chunks = state_data.get("confirmed_chunks", 0)
                        print(f"🔄 [Resume Match] Found existing sidecar tracking state. Resuming from chunk index: {confirmed_chunks}")
                except Exception:
                    confirmed_chunks = 0 # Fall back if state descriptor is unreadable
            
            # 3. Yell back the resume check data offset token to the sender node
            client_sock.sendall(f"{confirmed_chunks}".ljust(64).encode('utf-8'))
            
            # 4. Open file descriptors to write streaming chunks dynamically
            bytes_received = confirmed_chunks * self.chunk_size
            write_mode = 'ab' if confirmed_chunks > 0 else 'wb'
            
            with open(partial_path, write_mode) as f:
                while bytes_received < file_size:
                    chunk = client_sock.recv(self.chunk_size)
                    if not chunk:
                        break # Wi-Fi connection dropped mid-transfer
                        
                    f.write(chunk)
                    bytes_received += len(chunk)
                    confirmed_chunks += 1
                    
                    # Persist tracking status payload to the JSON sidecar descriptor file
                    with open(sidecar_path, 'w') as sf:
                        json.dump({
                            "filename": filename,
                            "total_size": file_size,
                            "confirmed_chunks": confirmed_chunks
                        }, sf)

            # 5. Pipeline Finalization Sequence
            if bytes_received >= file_size:
                final_destination = os.path.join(self.storage_dir, filename)
                # Safely rename partial file to its true final layout name
                if os.path.exists(final_destination):
                    os.remove(final_destination)
                os.rename(partial_path, final_destination)
                
                # Cleanup state sidecars cleanly
                if os.path.exists(sidecar_path):
                    os.remove(sidecar_path)
                print(f"✨ [Transfer Complete] '{filename}' successfully verified and saved!")
            else:
                print(f"⚠️ [Transfer Suspended] Link lost. State sidecar preserved at chunk check index: {confirmed_chunks}")
                
        except Exception as e:
            print(f"[Transfer Error] Handling incoming stream failed: {e}")
        finally:
            client_sock.close()

    def send_file(self, target_ip, file_path):
        """Sender Engine: Reads remote handshake parameters and streams chunks sequentially."""
        if not os.path.exists(file_path):
            print(f"[TCP Outbound] Error: Target file '{file_path}' not found.")
            return False
            
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        sender_thread = threading.Thread(
            target=self._stream_outbound_file, 
            args=(target_ip, file_path, filename, file_size), 
            daemon=True
        )
        sender_thread.start()
        return True

    def _stream_outbound_file(self, target_ip, file_path, filename, file_size):
        print(f"\n🚀 [TCP Outbound] Initiating stream tunnel to: {target_ip}:{self.port}...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((target_ip, self.port))
            
            # Send file metadata identification layout block
            header = f"{filename}|{file_size}".ljust(1024)
            sock.sendall(header.encode('utf-8'))
            
            # Listen for the receiver's handshake index configuration token
            handshake_response = sock.recv(64).decode('utf-8').strip()
            start_chunk = int(handshake_response)
            
            start_byte_offset = start_chunk * self.chunk_size
            bytes_sent = start_byte_offset
            
            if start_chunk > 0:
                print(f"⏭️ [Resume Sync] Target node reports partial progress. Seeking byte index: {start_byte_offset} bytes")
                
            with open(file_path, 'rb') as f:
                # Instantly reposition the file pointer stream to skip already-received data chunks
                f.seek(start_byte_offset)
                
                while bytes_sent < file_size:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    sock.sendall(chunk)
                    bytes_sent += len(chunk)
                    
            if bytes_sent >= file_size:
                print(f"✨ [Transfer Complete] Stream payload '{filename}' successfully sent to {target_ip}!")
            else:
                print(f"⚠️ [Transfer Terminated] Outbound pipe dropped at byte chunk checkpoint: {bytes_sent}/{file_size}")
                
        except Exception as e:
            print(f"[TCP Outbound Error] Engine failed to handshake or pipeline timed out: {e}")
        finally:
            sock.close()