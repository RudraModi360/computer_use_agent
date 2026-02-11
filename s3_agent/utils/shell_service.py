
import subprocess
import threading
import time
import os
import queue
import sys
import socket
import select
import json
import uuid

# Registry file
REGISTRY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".active_shells.json")

class NonBlockingStreamReader:
    def __init__(self, stream):
        self._s = stream
        self._q = queue.Queue()
        self._t = threading.Thread(target=self._populate_queue, daemon=True)
        self._t.start()
        
    def _populate_queue(self):
        for line in iter(self._s.readline, ''):
            if line:
                self._q.put(line)
                # Visible echo
                try:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                except: pass

    def readline(self, timeout=None):
        try:
            return self._q.get(block=timeout is not None, timeout=timeout)
        except queue.Empty:
            return None

    def clear(self):
        while not self._q.empty():
            try: self._q.get_nowait()
            except: pass

class ShellService:
    def __init__(self):
        # 1. Config
        self.host = '127.0.0.1'
        self.cmd_process = None
        
        # 2. Start Socket
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.bind((self.host, 0))
        self.port = self.server_sock.getsockname()[1]
        self.server_sock.listen(5)
        
        # 3. Register
        self._register()
        
        print(f"==================================================")
        print(f" MANAGED SHELL SATELLITE (PID: {os.getpid()})")
        print(f" Listening on Port: {self.port}")
        print(f"==================================================")
        
        # 4. Start CMD
        env = os.environ.copy()
        
        self.cmd_process = subprocess.Popen(
            "cmd.exe",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, 
            text=True,
            bufsize=1,
            env=env,
            cwd=os.getcwd()
        )
        
        self.reader = NonBlockingStreamReader(self.cmd_process.stdout)
        
        # 5. Loop
        threading.Thread(target=self._accept_loop, daemon=True).start()
        
        # Keep alive
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            self._cleanup()

    def _register(self):
        entries = []
        if os.path.exists(REGISTRY_FILE):
            try:
                with open(REGISTRY_FILE, 'r') as f:
                    entries = json.load(f)
            except: pass
            
        # Add self
        entry = {
            "pid": os.getpid(),
            "port": self.port,
            "cwd": os.getcwd(),
            "created": time.time()
        }
        entries.append(entry)
        
        with open(REGISTRY_FILE, 'w') as f:
            json.dump(entries, f)

    def _cleanup(self):
        # Remove from registry? Maybe not needed for simple persist logic
        if self.cmd_process:
            self.cmd_process.terminate()

    def _accept_loop(self):
        while True:
            conn, _ = self.server_sock.accept()
            # Handle in new thread to allow concurrent commands if needed (though CMD is single threaded)
            # Actually better to handle sequentially for CMD
            self._handle_client(conn)

    def _handle_client(self, conn):
        with conn:
            try:
                data = conn.recv(8192).decode('utf-8')
                if not data: return
                
                req = json.loads(data)
                cmd = req.get('command')
                
                if cmd:
                    print(f"\n[AGENT]: {cmd}")
                    
                    # Create unique marker
                    marker = f"__END_{uuid.uuid4().hex[:8]}__"
                    
                    # Clear previous output
                    self.reader.clear()
                    
                    # Write command
                    full_cmd = f"{cmd} & echo {marker}\n"
                    self.cmd_process.stdin.write(full_cmd)
                    self.cmd_process.stdin.flush()
                    
                    # Read until marker
                    captured = []
                    start_t = time.time()
                    
                    while True:
                        line = self.reader.readline(timeout=0.1)
                        if line:
                            # Ignore the command echo line
                            if marker in line and "& echo" not in line:
                                break
                            captured.append(line)
                        
                        if time.time() - start_t > 60:
                            captured.append("\n[Timeout]\n")
                            break
                    
                    # Send response
                    resp = json.dumps({"output": "".join(captured)})
                    conn.sendall(resp.encode('utf-8'))
                    
            except Exception as e:
                print(f"Error: {e}")
                err_resp = json.dumps({"output": f"Error: {e}"})
                conn.sendall(err_resp.encode('utf-8'))

if __name__ == "__main__":
    ShellService()
