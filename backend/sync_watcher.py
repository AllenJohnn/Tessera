import os
import time
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class TesseraFolderSyncHandler(FileSystemEventHandler):
    def __init__(self, local_ip):
        self.local_ip = local_ip
        # Target local web endpoint to safely fetch active network peers
        self.peers_api_url = f"http://127.0.0.1:5000/api/peers"

    def _get_active_peers(self):
        """Queries the local discovery node via API to find target destination IPs."""
        try:
            response = requests.get(self.peers_api_url, timeout=2)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return {}

    def _trigger_peer_sync(self, file_path):
        """Tells the local server to push this modified file to all discovered network nodes."""
        # Skip temporary files or system configuration directories
        if ".landrop" in file_path or ".git" in file_path:
            return

        peers = self._get_active_peers()
        if not peers:
            return

        print(f"\n⚡ [Sync Event] Detected change in: {os.path.basename(file_path)}")
        
        # Loop through every discovered PC on the LAN and trigger a chunked socket upload
        for peer_ip in peers.keys():
            try:
                sync_payload = {
                    "target_ip": peer_ip,
                    "file_path": os.path.abspath(file_path)
                }
                # Call our server's internal outbound endpoint to start the TCP stream
                requests.post("http://127.0.0.1:5000/api/send_peer", json=sync_payload, timeout=2)
                print(f"   ↳ Outbound sync signal dispatched to workstation: {peer_ip}")
            except Exception as e:
                print(f"   ❌ Failed to dispatch sync stream to {peer_ip}: {e}")

    # Intercept filesystem events natively provided by the OS kernel
    def on_created(self, event):
        if not event.is_directory:
            self._trigger_peer_sync(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._trigger_peer_sync(event.src_path)


def start_folder_sync_watcher(local_ip):
    """Spins up the OS-level filesystem event observer thread loop."""
    watch_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '../sync_watch'))
    os.makedirs(watch_folder, exist_ok=True)

    event_handler = TesseraFolderSyncHandler(local_ip)
    observer = Observer()
    observer.schedule(event_handler, path=watch_folder, recursive=True)
    observer.start()
    print(f"[Sync Watcher] Active. Monitoring local directory: {watch_folder}")
    return observer