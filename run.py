import uvicorn
import webbrowser
import threading
import time

def open_browser():
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 QUANT DESK: Multi-Agent Mock Trading Swarm")
    print("⚡ Web Dashboard: http://127.0.0.1:8000")
    print("Press Ctrl+C to stop.")
    print("=" * 60)
    
    # Auto launch browser in a thread
    threading.Thread(target=open_browser, daemon=True).start()
    
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=True)
