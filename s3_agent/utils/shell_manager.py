
import subprocess
import threading
import time
import os
import queue
import sys
import socket
import json
from typing import Optional, List, Dict

# Path to the satellite service script
SERVICE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shell_service.py")
REGISTRY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".active_shells.json")

class SatelliteShell:
    """
    Connects to a running 'shell_service.py' satellite via socket.
    This ensures the shell is visible (as it runs in its own window) but controllable.
    """
    def __init__(self, port: int, pid: int):
        self.port = port
        self.pid = pid
        self.is_busy = False

    def execute(self, command: str, timeout: int = 60) -> str:
        if self.is_busy:
            return "Error: Shell is busy."
        
        self.is_busy = True
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout + 5)
                s.connect(('127.0.0.1', self.port))
                
                req = json.dumps({"command": command})
                s.sendall(req.encode('utf-8'))
                
                # Receive response (buffered)
                chunks = []
                while True:
                    chunk = s.recv(4096)
                    if not chunk: break
                    chunks.append(chunk)
                
                data = b"".join(chunks).decode('utf-8')
                resp = json.loads(data)
                return resp.get("output", "")
                
        except (ConnectionRefusedError, BrokenPipeError, ConnectionResetError):
            print("[Shell] Connection lost to satellite (User closed window?)")
            return "Error: Connection lost"
        except Exception as e:
            return f"Error communicating with satellite: {e}"
        finally:
            self.is_busy = False

    def is_alive(self):
        """Check if process is still running"""
        import psutil
        return psutil.pid_exists(self.pid)

class ShellManager:
    """Singleton to manage satellite shells"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ShellManager, cls).__new__(cls)
            cls._instance.shells = []
        return cls._instance

    def get_available_shell(self) -> SatelliteShell:
        """Get an idle shell or spawn a new visible satellite"""
        
        # 1. Sync with registry
        self._sync_shells()
        
        # 2. Check for idle
        for shell in self.shells:
            if not shell.is_busy:
                return shell
        
        # 3. Spawn new visible satellite
        print("[ShellManager] Spawning new Visible Shell Satellite...")
        
        # CREATE_NEW_CONSOLE ensures it pops up independently
        subprocess.Popen(
            [sys.executable, SERVICE_SCRIPT],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            cwd=os.getcwd()
        )
        
        # Wait for it to register
        for _ in range(10): # wait up to 5s
            time.sleep(0.5)
            self._sync_shells()
            # If we found a new ones, return the first idle one
            for shell in self.shells:
                if not shell.is_busy:
                    return shell
                    
        raise Exception("Failed to spawn and connect to Shell Satellite")

    def _sync_shells(self):
        """Read registry file and update internal list"""
        if not os.path.exists(REGISTRY_FILE):
            return

        try:
            with open(REGISTRY_FILE, 'r') as f:
                entries = json.load(f)
            
            # Simple reconciliation
            # We assume registry is truth, but we keep our instances if they match
            current_ports = {s.port: s for s in self.shells}
            new_shells = []
            
            for entry in entries:
                pid = entry.get('pid')
                port = entry.get('port')
                
                # Skip invalid
                if not pid or not port: continue
                
                # Check if process alive
                import psutil
                if not psutil.pid_exists(pid):
                    continue
                    
                if port in current_ports:
                    new_shells.append(current_ports[port])
                else:
                    new_shells.append(SatelliteShell(port, pid))
            
            self.shells = new_shells
            
        except Exception as e:
            print(f"Error syncing shells: {e}")

