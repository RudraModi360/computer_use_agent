
import socket
import subprocess
import json
import os
import sys
import threading
import time

# Registry file to store active shell info
# Using relative path to find it in utils/.. directory
REGISTRY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".active_shells.json")

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def register_shell(port, pid):
    """Register this shell in the json file"""
    entries = []
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, 'r') as f:
                entries = json.load(f)
        except:
            entries = []
    
    entries.append({"port": port, "pid": pid})
    
    try:
        with open(REGISTRY_FILE, 'w') as f:
            json.dump(entries, f)
    except Exception as e:
        print(f"Error registering shell: {e}")

def remove_shell(port):
    """Remove this shell from registry on exit"""
    if not os.path.exists(REGISTRY_FILE):
        return
    
    try:
        with open(REGISTRY_FILE, 'r') as f:
            entries = json.load(f)
        
        entries = [e for e in entries if e['port'] != port]
        
        with open(REGISTRY_FILE, 'w') as f:
            json.dump(entries, f)
    except:
        pass

def run_command(command):
    """Run command in subprocess and capture output"""
    try:
        # We use shell=True to support internal commands like 'dir', 'echo'
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
            cwd=os.getcwd()
        )
        stdout, stderr = process.communicate(timeout=60)
        output = stdout + stderr
        return output.strip()
    except Exception as e:
        return f"Error executing command: {e}"

def start_server():
    # Redirect stdout/stderr to log file for debugging (especially when hidden)
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nexus_shell.log")
    sys.stdout = open(log_file, "a", encoding="utf-8", buffering=1)
    sys.stderr = sys.stdout
    
    port = find_free_port()
    pid = os.getpid()
    
    print(f"--- NEXUS SHELL SATELLITE ---")
    print(f"Time: {time.ctime()}")
    print(f"PID: {pid}")
    print(f"Port: {port}")
    print(f"Status: READY")
    print("-" * 30)
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('127.0.0.1', port))
    server.listen(1)
    
    # Register only AFTER listening
    register_shell(port, pid)
    
    try:
        while True:
            client, addr = server.accept()
            print(f"Connection from {addr}")
            
            # ... rest of loop ...
            data = client.recv(4096).decode('utf-8')
            if not data:
                break
                
            try:
                msg = json.loads(data)
                cmd = msg.get('command')
                
                print(f"> {cmd}")
                output = run_command(cmd)
                print(output)
                print("-" * 30)
                
                response = json.dumps({"output": output})
                client.sendall(response.encode('utf-8'))
            except Exception as e:
                print(f"Error processing command: {e}")
                err_resp = json.dumps({"output": f"Server Error: {e}"})
                client.sendall(err_resp.encode('utf-8'))
            finally:
                client.close()
                
    except Exception as e:
        print(f"Server Fatal Error: {e}")
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        remove_shell(port)
        server.close()

if __name__ == "__main__":
    start_server()
