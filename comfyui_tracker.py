#!/usr/bin/env python3
# comfyui_live_monitor_fixed.py
# --------------------------------------------------------------
# Monitors ComfyUI execution, displays live previews via OpenCV,
# saves all execution events + results.json on success or exit.
# Uses websocket-client (stable), handles fragmented JPEG frames.
# --------------------------------------------------------------

import json
import uuid
import time
import threading
import signal
import sys
import requests
import cv2
import numpy as np
import websocket
from pathlib import Path

# ---------------- CONFIG ----------------
COMFYUI_HOST = "10.2.0.237"   # change to your ComfyUI host
COMFYUI_PORT = 8188
WORKFLOW_PATH = "T2I_SDXL.json"
RESULTS_PATH = "info.json"
# -----------------------------------------

# Global state
execution_data = {
    "prompt_id": None,
    "events": [],
    "result_data": {},
    "error": None
}

stop_event = threading.Event()
preview_lock = threading.Lock()
preview_image = None

# persistent JPEG buffer for assembling fragmented JPEGs
jpeg_buffer = b""

# ---------------- save + cleanup ----------------
def save_results():
    try:
        with open(RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(execution_data, f, indent=2)
        print(f"\n💾 Results written to {RESULTS_PATH}")
    except Exception as e:
        print(f"[ERROR] Failed saving results: {e}")

def graceful_exit(*_):
    print("\n🛑 Exiting monitor...")
    stop_event.set()
    save_results()
    try:
        cv2.destroyAllWindows()
    except:
        pass
    # do not call sys.exit here when called from non-main threads in websocket callbacks
    # but if main calls graceful_exit we want to exit
    try:
        sys.exit(0)
    except SystemExit:
        pass

signal.signal(signal.SIGINT, graceful_exit)

# ---------------- fetch final history ----------------
def fetch_results(prompt_id):
    url = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}/history/{prompt_id}"
    for i in range(10):
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200 and r.text.strip():
                data = r.json()
                if data:
                    execution_data["result_data"] = data
                    print(f"[FETCH] Retrieved final result for prompt_id={prompt_id}")
                    return True
        except Exception as e:
            print(f"[WARN] Fetch attempt {i+1} failed: {e}")
        time.sleep(1)
    return False

# ---------------- queue workflow ----------------
def queue_workflow(client_id):
    wf_path = Path(WORKFLOW_PATH)
    if not wf_path.exists():
        raise FileNotFoundError(f"Workflow file not found: {wf_path.resolve()}")
    with open(wf_path, "r", encoding="utf-8") as f:
        workflow = json.load(f)
    url = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}/prompt"
    payload = {"prompt": workflow, "client_id": client_id}
    r = requests.post(url, json=payload)
    r.raise_for_status()
    print("[INFO] Workflow queued successfully.")

# ---------------- preview window (main thread) ----------------
def preview_window():
    print("[INFO] Live preview — press 'q' or ESC to quit.")
    cv2.namedWindow("🧠 ComfyUI Live Preview", cv2.WINDOW_AUTOSIZE)
    while not stop_event.is_set():
        with preview_lock:
            frame = preview_image  # local ref
        if frame is not None:
            try:
                cv2.imshow("🧠 ComfyUI Live Preview", frame)
            except cv2.error:
                # if display breaks, print and continue (we still save images if needed)
                print("[WARN] OpenCV error while showing frame")
        key = cv2.waitKey(30) & 0xFF
        if key in (ord("q"), 27):
            graceful_exit()
            break
    try:
        cv2.destroyAllWindows()
    except:
        pass

# ---------------- websocket handlers ----------------
def on_open(ws):
    print("[OPEN] Connected to ComfyUI WebSocket")

def on_close(ws, code, msg):
    print(f"[CLOSE] code={code} msg={msg}")

def on_error(ws, error):
    print("[WS ERROR]", error, file=sys.stderr)

def on_message(ws, message):
    """
    message: bytes or str
    This function runs inside websocket-client thread.
    We modify global jpeg_buffer and preview_image.
    """
    global jpeg_buffer, preview_image

    # debug print for message type
    try:
        if isinstance(message, (bytes, bytearray)):
            print(f"[DEBUG] message type: <class 'bytes'> size={len(message)}")
        else:
            print(f"[DEBUG] message type: <class 'str'> size=text")
    except Exception:
        pass

    # ---------------- handle binary fragments ----------------
    if isinstance(message, (bytes, bytearray)):
        # append
        jpeg_buffer += message

        # find start and end markers
        start = jpeg_buffer.find(b"\xff\xd8")  # JPG SOI
        end = jpeg_buffer.find(b"\xff\xd9")    # JPG EOI

        # If there is at least one complete JPEG, extract and decode the first
        if start != -1 and end != -1 and end > start:
            frame_data = jpeg_buffer[start:end + 2]
            # trim the processed bytes (may leave next frame fragment)
            jpeg_buffer = jpeg_buffer[end + 2:]

            try:
                arr = np.frombuffer(frame_data, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None:
                    with preview_lock:
                        preview_image = img
                    print(f"[FRAME] Decoded preview {img.shape}")
                else:
                    print("[WARN] Decoded image is None")
            except Exception as e:
                print(f"[ERROR] Failed to decode frame: {e}")
        # else: wait for more fragments
        return

    # ---------------- handle text/json messages ----------------
    try:
        data = json.loads(message)
    except Exception:
        print("[TEXT]", message)
        return

    msg_type = data.get("type")
    msg_data = data.get("data", {})

    # skip noisy telemetry by default
    if msg_type == "crystools.monitor":
        return

    # handle important message types and store them
    if msg_type == "execution_start":
        pid = msg_data.get("prompt_id")
        execution_data["prompt_id"] = pid
        print(f"\n[START] Execution started → {pid}")
        execution_data["events"].append({"event": "execution_start", "prompt_id": pid})

    elif msg_type == "executing":
        node = msg_data.get("node")
        print(f"[NODE] Executing node: {node}")
        execution_data["events"].append({"event": "executing", "node": node})

    elif msg_type == "execution_progress":
        val, total = msg_data.get("value"), msg_data.get("max")
        print(f"[PROGRESS] {val}/{total}")
        execution_data["events"].append({"event": "progress", "current": val, "total": total})

    elif msg_type in ("execution_success", "execution_complete", "execution_finished"):
        # handle different ComfyUI variations; prefer execution_success if present
        pid = msg_data.get("prompt_id") or execution_data.get("prompt_id")
        print(f"\n[✅ SUCCESS] Execution success for prompt_id={pid}")
        execution_data["events"].append({"event": "execution_success", "data": msg_data})
        # fetch history (best-effort) and save
        if pid and fetch_results(pid):
            save_results()
        else:
            save_results()

    elif msg_type == "execution_error":
        print(f"[❌ ERROR] {msg_data}")
        execution_data["error"] = msg_data
        execution_data["events"].append({"event": "error", "data": msg_data})
        save_results()

    else:
        # general logging for other types
        print(f"[INFO] {msg_type}: {msg_data}")
        execution_data["events"].append({"event": msg_type, "data": msg_data})

# ---------------- main ----------------
def main():
    client_id = str(uuid.uuid4())
    ws_url = f"ws://{COMFYUI_HOST}:{COMFYUI_PORT}/ws?clientId={client_id}"
    print(f"[INFO] Connecting to {ws_url}")

    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    # run websocket listener in background thread
    ws_thread = threading.Thread(target=ws.run_forever, kwargs={"ping_interval": 30}, daemon=True)
    ws_thread.start()

    # give time for connection
    time.sleep(1.0)

    # queue workflow using same client id
    try:
        queue_workflow(client_id)
    except Exception as e:
        print(f"[ERROR] Could not queue workflow: {e}")
        graceful_exit()

    # launch preview in main thread (OpenCV requires main thread on macOS)
    try:
        preview_window()
    except Exception as e:
        print(f"[ERROR] preview loop failed: {e}")
    finally:
        # cleanup: close ws and save
        try:
            ws.close()
        except:
            pass
        ws_thread.join(timeout=2)
        graceful_exit()

if __name__ == "__main__":
    main()
