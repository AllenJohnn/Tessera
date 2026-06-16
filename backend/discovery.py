import socket
import time
import json
import threading

class UDPDiscoveryEngine:
    def __init__(self, local_ip, hostname):
        self.local_ip = local_ip
        self.hostname = hostname
        
        # Ports matched exactly to your Tessera blueprint layout
        self.discovery_port = 5001 
        self.socket_port = 6000
        self.stale_timeout = 30 # Drop peers silent for 30s
        
        # Thread-safe container for mapping live network peers
        self.peer_registry = {}
        self.lock = threading.Lock()
        
        self.running = False

    def start_broadcaster(self):
        """Spins up a background worker thread to broadcast existence to the subnet."""
        self.running = True
        broadcaster_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        broadcaster_thread.start()
        print("[Discovery Engine] UDP Heartbeat Beacon activated.")

    def start_listener(self):
        """Spins up a background listener socket to track foreign Tessera nodes."""
        listener_thread = threading.Thread(target=self._listener_loop, daemon=True)
        listener_thread.start()
        print("[Discovery Engine] Local Subnet Packet Listener active.")

    def _broadcast_loop(self):
        # Instantiate raw UDP socket configured for network broadcasting
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        # Target the global subnet broadcast mask
        broadcast_address = ('255.255.255.255', self.discovery_port)
        
        payload = {
            "hostname": self.hostname,
            "ip": self.local_ip,
            "port": self.socket_port,
            "version": "1.0"
        }
        
        while self.running:
            try:
                msg = json.dumps(payload).encode('utf-8')
                sock.sendto(msg, broadcast_address)
            except Exception as e:
                print(f"\n[Discovery Fault] Broadcaster encountered an issue: {e}")
            time.sleep(5) # 5-second pulse intervals from blueprint
            
        sock.close()

    def _listener_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # Bind to all local interfaces on the custom discovery channel
        sock.bind(('0.0.0.0', self.discovery_port))
        
        while self.running:
            try:
                data, addr = sock.recvfrom(2048)
                sender_ip = addr[0]
                
                # Filter out our own heartbeat echo loops
                if sender_ip == self.local_ip:
                    continue
                    
                payload = json.loads(data.decode('utf-8'))
                
                with self.lock:
                    if sender_ip not in self.peer_registry:
                        print(f"\n✨ [Peer Discovered] Managed node '{payload['hostname']}' registered at {sender_ip}")
                    
                    # Store data tracking structure and map timestamp
                    self.peer_registry[sender_ip] = {
                        "hostname": payload['hostname'],
                        "port": payload['port'],
                        "last_seen": time.time()
                    }
            except Exception as e:
                if self.running:
                    print(f"[Discovery Fault] Listener interface tracking exception: {e}")
                    
        sock.close()

    def get_active_peers(self):
        """Sweeps cache to prune stale items and returns validated active nodes."""
        current_time = time.time()
        with self.lock:
            # Purge any workstation that drops offline for more than 30 seconds
            stale_nodes = [ip for ip, data in self.peer_registry.items() 
                           if current_time - data['last_seen'] > self.stale_timeout]
            for ip in stale_nodes:
                print(f"\n🍂 [Peer Dropped] Connection to host '{self.peer_registry[ip]['hostname']}' timed out.")
                del self.peer_registry[ip]
                
            return {ip: {"hostname": d["hostname"], "port": d["port"]} for ip, d in self.peer_registry.items()}