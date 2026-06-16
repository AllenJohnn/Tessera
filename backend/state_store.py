import sqlite3
import os
import time

class TesseraStateStore:
    def __init__(self):
        # Place database exactly where the blueprint specifies
        self.db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../.landrop_state'))
        os.makedirs(self.db_dir, exist_ok=True)
        self.db_path = os.path.join(self.db_dir, 'landrop.db')
        self._init_db()

    def _get_connection(self):
        """Returns a thread-safe connection instance to the local SQLite file."""
        # check_same_thread=False allows multiple server background threads to write safely
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row # Allows dictionary-like row querying
        return conn

    def _init_db(self):
        """Initializes structural tracking tables defined in the project blueprint."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 1. Historical transfer tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                total_chunks INTEGER,
                confirmed_chunks INTEGER,
                status TEXT,
                peer_ip TEXT,
                started_at REAL
            )
        ''')
        
        # 2. Network Peer Cache table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS peers (
                ip TEXT PRIMARY KEY,
                hostname TEXT,
                last_seen REAL,
                port INTEGER
            )
        ''')
        
        # 3. Synchronized folder event transactions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                path TEXT,
                timestamp REAL,
                peer_ip TEXT,
                synced INTEGER DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()

    def log_transfer(self, filename, total_chunks, status, peer_ip):
        """Inserts or logs a fresh transaction token into the transfer database table."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO transfers (filename, total_chunks, confirmed_chunks, status, peer_ip, started_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (filename, total_chunks, total_chunks if status=='completed' else 0, status, peer_ip, time.time()))
        conn.commit()
        conn.close()

    def get_transfer_history(self):
        """Retrieves recent file sync records for presentation in the web dashboard interface."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM transfers ORDER BY started_at DESC LIMIT 10')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]