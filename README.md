# Waterfall - Local AI Agent - Music Visualizer

A Python-based agentic AI assistant running locally with Ollama + Nemotron-nano, featuring a stunning fractal visualization background synced to music.

## Spec Requirements

- You need at least 24gb of VRAM to run the AI agent (The music visualizer will work without it).
- You need at least 8gb of RAM to run this.
- It will run perfectly on a RTX 4090, as that is what it was developed on.

## Demo: https://www.youtube.com/watch?v=KUdn1FoSJSo

## Features

- 🌀 **Fractal Visualization** - Deep-zoom Julia set fractal with audio-reactive effects
- 🎵 **Music Integration** - Beat-synced ripples, morphing, and zoom effects
- 🌐 **Browser Automation** - Navigate, click, type, take screenshots
- 📁 **File System** - Read, write, search files
- 📝 **Grading** - Parse DOCX rubrics and grade submissions
- 🎮 **Game Control** - Keyboard/mouse input, window focus (cross-platform)
- 📷 **Vision** - Screenshots and image handling
- ⚙️ **Settings Panel** - Real-time control of visual effects and LLM parameters

## Setup

### Windows

1. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Make sure Ollama is running:**

   ```bash
   ollama serve
   ```

3. **Run the Pro UI:**

   ```bash
   python ui_pro.py
   ```

4. Open <http://127.0.0.1:7860> in your browser.

### Linux

1. **Install system dependencies:**

   ```bash
   # For game control features (optional)
   sudo apt install wmctrl xdotool
   
   # For pyautogui (screenshot/input)
   sudo apt install python3-tk python3-dev scrot python3-venv python3-full
   ```

2. **Create and activate a virtual environment:**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Python dependencies:**

   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Make sure Ollama is running:**

   ```bash
   ollama serve
   ```

5. **Run the Pro UI:**

   ```bash
   python ui_pro.py
   ```

6. Open <http://127.0.0.1:7860> in your browser.

> **Note:** Each time you open a new terminal, activate the venv with: `source venv/bin/activate`

### macOS

1. **Install Homebrew** (if not already installed):

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

2. **Install Python and dependencies:**

   ```bash
   brew install python3
   ```

3. **Create and activate a virtual environment:**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

4. **Install Python dependencies:**

   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

5. **Grant accessibility permissions:**
   - Go to System Preferences → Security & Privacy → Privacy → Accessibility
   - Add Terminal (or your terminal app) to the list

6. **Make sure Ollama is running:**

   ```bash
   ollama serve
   ```

7. **Run the Pro UI:**

   ```bash
   python ui_pro.py
   ```

8. Open <http://127.0.0.1:7860> in your browser.

> **Note:** Each time you open a new terminal, activate the venv with: `source venv/bin/activate`

## UI Controls

### Hidden Buttons (hover to reveal)

- **Top Right** - Hide/Show UI
- **Top Left** - Settings Panel (⚙️)

### Settings Panel

**Fractal Settings:**

- Enable/Disable fractal animation
- Morph Intensity (-10 to 10) - Audio-reactive morphing speed
- Ripple Intensity (-10 to 10) - Beat-triggered ripple effect
- Bass Zoom Intensity (-10 to 10) - Bass-reactive zoom punch
- Config display from `fractal_config.json`
- Refresh Effects button

**LLM Settings:**

- System Prompt editor
- Temperature (0-2)
- Context Length (512-8192)

## Usage

Just type natural language commands like:

- "List the files in the current directory"
- "Open google.com and search for Python tutorials"
- "Grade the submission in student_work.docx using the Avogadro rubric"
- "Focus the Notepad window and type 'Hello World'"

## Files

- `ui_pro.py` - Pro Gradio web interface with fractal visualization
- `agent.py` - Main agent loop with tool execution
- `ollama_client.py` - Ollama API wrapper with configurable parameters
- `fractal_config.json` - Fractal visualization parameters
- `tools/` - Tool implementations
  - `browser.py` - Playwright browser automation
  - `filesystem.py` - File operations
  - `grading.py` - Rubric parsing and grading
  - `gamecontrol.py` - Keyboard/mouse/window control (cross-platform)
  - `vision.py` - Screenshot utilities

## Platform Support

| Feature            | Windows | Linux               | macOS               |
|--------------------|---------|---------------------|---------------------|
| Fractal Visualizer | ✅      | ✅                  | ✅                  |
| Music Sync         | ✅      | ✅                  | ✅                  |
| AI Agent           | ✅      | ✅                  | ✅                  |
| Browser Automation | ✅      | ✅                  | ✅                  |
| Window Control     | ✅      | ✅ (wmctrl/xdotool) | ✅ (AppleScript)    |
| Game Input         | ✅      | ✅ (pyautogui)      | ✅ (pyautogui)      |


## Support

If you enjoy this project, consider supporting development:

💝 [Donate via Venmo](https://venmo.com/code?user_id=2272974967144448513&created=1768270538)
