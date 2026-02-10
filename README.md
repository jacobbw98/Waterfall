# Waterfall - Local AI Agent - Music Visualizer

A Python-based agentic AI assistant running locally with Ollama + Nemotron-nano, featuring a stunning fractal visualization background synced to music.

## Spec Requirements

- Requires at least 24gb of VRAM for optimal performance (The music visualizer will work without it).
- Requires at least 8gb of RAM.
- Developed and tested on RTX 4090 but compatible with other setups.

<<<<<<< HEAD
## Demo
[Link to demo video]
=======
## Demo: [https://www.youtube.com/watch?v=KUdn1FoSJSo](https://youtu.be/09YM7YPSbWw)
>>>>>>> 32139ff4ee3603539f11c2e2d040de11552ed209

## Features

- 🌀 **Fractal Visualization** - Deep-zoom Julia set fractal with audio-reactive effects
- 🎵 **Music Integration** - Beat-synced ripples, morphing, and zoom effects across all supported music tracks
- 🌐 **Browser Automation** - Navigate, click, type, take screenshots of any website
- 📁 **File System** - Read, write, search files on your system including cross-platform control
- 📝 **Grading** - Parse DOCX rubrics and grade student submissions automatically
- 🎮 **Game Control** - Keyboard/mouse input simulation with window focus management across platforms
- 📷 **Vision** - Screenshot utilities for image recognition tasks

## Project Structure Highlights

The project includes key components:
- `ui_pro.py`: Pro Gradio web interface with fractal visualization
- `agent.py`: Main agent loop that executes tool calls (now supports browser automation, file system operations, and more)
- Comprehensive tools suite including browser control, grading, game input, vision processing, and memory management

## Setup Instructions Overview

### Cross-platform Setup
<details>
<summary>Windows</summary>

1. Install dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
```

2. Start Ollama server:
```bash
ollama serve
```

3. Run Pro UI:
```bash
python ui_pro.py
```

4. Access at <http://127.0.0.1:7872>
</details>

<details>
<summary>Linux</summary>

1. Install system dependencies and setup environment
</details>

<details>
<summary>macOS</summary>

2. Install Homebrew and Python dependencies (if applicable)
<details>
<summary>Details</summary></details>
</details>

## Usage Examples

Test browser navigation:
"Navigate to https://example.com"

Test music sync features:
"Play/pause background track when tempo changes"

AI interaction example: 
"I'd like to analyze this image and describe it"

## Platform Support Matrix

| Feature            | Windows | Linux   | macOS   |
|--------------------|---------|---------|---------|
| Fractal Visualizer | ✅      | ✅      | ✅      |
| Music Sync         | ✅      | ✅      | ✅      |
| Browser Automation | ✅      | ✅      | ✅      |
| AI Agent           | ✅      | ✅      | ✅      |
| Cross-platform Control | ✅ | ✅ (wmctrl/xdotool) | ✅ (AppleScript) |

</details>

## Support

If you enjoy this project, consider supporting development:
[Donation Link]

<environment_details>
# Antigravity Visible Files
(No visible files)

# Antigravity Open Tabs
goal_tracker.py
test_raw_http.py
test_stream.py
test_minimal.py
test_nemotron.py

ui_pro.py
fractal_config.json
gradio_fractal_demo.py
fractal_shader.js
README.md
Music/...
...

# Current Time
2/10/2026, 9:54:38 AM (Pacific/Honolulu, UTC-10:00)

# Context Window Usage
25,760 / 32.768K tokens used (79%)

# Current Mode
ACT MODE
</environment_details>
</write_to_file>