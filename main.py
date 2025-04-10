from flask import Flask, request, Response
import requests
import subprocess
import time
import atexit
import signal
import os
from dotenv import load_dotenv

app = Flask(__name__)
# Configuration
TARGET_PORT = 4000  # Change this to the port of your target service
TARGET_HOST = '127.0.0.1'  # Change if needed
TARGET_URL = f'http://{TARGET_HOST}:{TARGET_PORT}'

# Target service command - replace with your actual command
TARGET_SERVICE_CMD = ['uv', 'run', 'litellm']
target_process = None

load_dotenv()

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
def proxy(path):
    # Forward the request to the target service
    url = f'{TARGET_URL}/{path}'
    
    # Get the request headers
    headers = {key: value for key, value in request.headers if key != 'Host'}
    
    # Forward the request with the same method, headers, and body
    resp = requests.request(
        method=request.method,
        url=url,
        headers=headers,
        data=request.get_data(),
        cookies=request.cookies,
        params=request.args,
        allow_redirects=False,
        stream=True
    )
    
    # Create a Flask response object
    excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
    response_headers = {
        name: value for name, value in resp.raw.headers.items()
        if name.lower() not in excluded_headers
    }
    
    # Return the response
    return Response(
        resp.content,
        resp.status_code,
        response_headers
    )

def start_target_service():
    """Start the target service as a subprocess"""
    global target_process
    print(f"Starting target service on port {TARGET_PORT}...")

    env_vars = os.environ.copy()
    
    # Start the target service as a subprocess
    target_process = subprocess.Popen(
        TARGET_SERVICE_CMD,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env_vars,
        preexec_fn=os.setsid  # Use process group for cleaner termination on Unix
    )
    
    # Wait a moment for the service to start
    time.sleep(2)
    
    if target_process.poll() is not None:
        # Process already exited - there was an error
        stdout, stderr = target_process.communicate()
        print(f"Target service failed to start: {stderr.decode()}")
        exit(1)
    
    print(f"Target service started with PID {target_process.pid}")
    return target_process

def cleanup_target_service():
    """Terminate the target service when the proxy exits"""
    global target_process
    if target_process:
        print(f"Stopping target service (PID {target_process.pid})...")
        
        try:
            # Try to terminate the process group cleanly on Unix
            os.killpg(os.getpgid(target_process.pid), signal.SIGTERM)
        except (AttributeError, OSError):
            # Fallback for Windows or other errors
            target_process.terminate()
        
        # Wait for process to terminate
        target_process.wait(timeout=5)
        print("Target service stopped")

if __name__ == '__main__':
    # Change the port to whatever you want the proxy to listen on
    PROXY_PORT = 8888
    
    # Start the target service first
    start_target_service()
    
    # Register the cleanup function to be called on exit
    atexit.register(cleanup_target_service)
    
    # Start the Flask app
    print(f"Starting proxy on port {PROXY_PORT}, forwarding to {TARGET_URL}")
    app.run(host='0.0.0.0', port=PROXY_PORT, debug=True)
