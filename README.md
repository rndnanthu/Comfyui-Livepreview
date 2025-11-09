# ComfyUI Tracker

A real-time monitoring tool for ComfyUI workflows that displays live previews and tracks execution progress.


![Screenshot](https://iili.io/KbMutHB.md.png)

## Overview

ComfyUI Tracker is a Python application that:
- Connects to a ComfyUI instance via WebSocket
- Monitors workflow execution in real-time
- Displays live previews of generated images using OpenCV
- Tracks execution events and saves results to a JSON file
- Handles fragmented JPEG frames for proper preview rendering

## Features

- **Real-time Preview**: Displays live previews of image generation using OpenCV
- **Event Tracking**: Records all execution events including start, progress, success, and errors
- **Result Persistence**: Saves execution data, events, and results to `info.json`
- **Fragmented Frame Handling**: Properly assembles fragmented JPEG frames from ComfyUI
- **Graceful Shutdown**: Handles SIGINT (Ctrl+C) for clean exit and data saving

## Requirements

- Python 3.7+
- ComfyUI instance running on a network-accessible host

## Installation

1. Install the required Python packages:
```bash
pip install -r requirements.txt
```

Or install them individually:
```bash
pip install opencv-python websocket-client requests numpy
```

2. Ensure you have a ComfyUI instance running at the configured host/port

3. Prepare your workflow file (default: `T2I_SDXL.json`)

## Configuration

Edit the configuration constants at the top of `comfyui_tracker.py`:

- `COMFYUI_HOST`: The IP address of your ComfyUI instance (default: "10.2.0.237")
- `COMFYUI_PORT`: The port of your ComfyUI instance (default: 8188)
- `WORKFLOW_PATH`: Path to your workflow JSON file (default: "T2I_SDXL.json")
- `RESULTS_PATH`: Path where execution results will be saved (default: "info.json")

## Usage

1. Make sure your ComfyUI instance is running
2. Ensure your workflow JSON file is available at the configured path
3. Run the tracker:

```bash
python comfyui_tracker.py
```

4. A preview window will open showing live updates of the generation process
5. Press 'q' or ESC to quit the preview window
6. Execution results will be saved to `info.json`

## Output

The tracker saves execution data to `info.json` with the following structure:
- `prompt_id`: The ID of the execution
- `events`: Array of all events during execution (start, progress, nodes executed, etc.)
- `result_data`: Final results fetched from ComfyUI history
- `error`: Any error information if execution failed

## File Structure

```
ComfyPreview/
├── comfyui_tracker.py      # Main application file
├── T2I_SDXL.json          # Example workflow file
├── requirements.txt       # Python dependencies
├── README.md             # This file
└── info.json             # Generated execution results (created at runtime)
```

## Dependencies

The script requires the following Python packages:
- websocket-client: For WebSocket communication with ComfyUI
- opencv-python: For displaying live preview images
- numpy: For image processing operations
- requests: For HTTP communication with ComfyUI API
