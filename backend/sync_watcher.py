import os
import time
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class TesseraFolderHandler(FileSystemEventHandler):
    def __init__(self, local_ip, storage_dir):
        self.local_ip = local_ip
        self.storage_dir = storage_dir
        self.last_triggered = {}

    def on_created(self, event):
        if event.is_directory:
            return
        self._process_sync_event(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        self._process_sync_event(event.src_path)

    def _process_sync_event(self, src_path):
        filename = os.path.basename(src_path)
        
        # Debounce multiple consecutive kernel mod ticks
        now = time.time()
        if filename in self.last_triggered and now - self.last_triggered[filename] < 2:
            return
        self.last_triggered[filename] = now

        # Wait briefly for file write handles to release gracefully
        time.sleep(0.5)
        if not os.path.exists(src_path) or os.path.getsize(src_path) == 0:
            return

        print(f"[Sync Watcher] Active system mutation detected on file: {filename}")
        
        # Access global server memory variables to locate network peer maps
        from server import discovery_node, transfer_node
        if discovery_node and transfer_node:
            active_peers = discovery_node.get_active_peers()
            if not active_peers:
                print("[Sync Watcher] File changed locally, but no desktop network peers are active.")
                return

            for peer_ip in active_peers.keys():
                print(f"[Auto Sync] Routing copy of '{filename}' directly down mesh line to: {peer_ip}")
                # Spin off execution into independent threads to keep filesystem monitoring non-blocking
                threading.Thread(
                    target=transfer_node.send_file, 
                    args=(peer_ip, src_path), 
                    daemon=True
                ).start()

def start_folder_sync_watcher(local_ip, watch_folder='../sync_watch'):
    """Spins up a permanent, non-blocking background folder monitor daemon."""
    target_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), watch_folder))
    os.makedirs(target_dir, exist_ok=True)

    event_handler = TesseraFolderHandler(local_ip, target_dir)
    observer = Observer()
    observer.schedule(event_handler, path=target_dir, recursive=False)
    observer.start()
    
    print(f"[Sync Watcher] Active. Monitoring local directory: {target_dir}")
    return observer