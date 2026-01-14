"""
Pro Agent UI - Split-screen with Thought Stream and Live Visual Feed.
"""
import gradio as gr
import base64
import os
import time
from agent import Agent
from ollama_client import list_models, DEFAULT_MODEL
from tools.vision import get_vision
from tools.gamecontrol import get_gamecontrol


class ProAgentUI:
    """Pro UI with split-screen layout."""
    
    def __init__(self):
        self.agent = Agent()
        self.vision = get_vision()
        self.game = get_gamecontrol()
        self.current_screenshot = None
        self.thought_log = []
        self.is_running = False
        self.planning_mode = False
        self.waiting_for_human = False  # Flag for human takeover
        
    def add_thought(self, thought_type: str, content: str):
        """Add a thought to the log."""
        timestamp = time.strftime("%H:%M:%S")
        icon = {
            "thinking": "🧠",
            "tool": "🔧",
            "result": "📋",
            "plan": "📝",
            "action": "⚡",
            "complete": "✅",
            "error": "❌",
            "pause": "⏸️",
            "resume": "▶️"
        }.get(thought_type, "💭")
        
        thought_line = f"[{timestamp}] {icon} {content}"
        self.thought_log.append(thought_line)
        print(thought_line)  # Console output
        if len(self.thought_log) > 50:
            self.thought_log = self.thought_log[-50:]
    
    def get_thought_stream(self) -> str:
        """Get formatted thought stream."""
        return "\n".join(self.thought_log) if self.thought_log else "Waiting for input..."
    
    def capture_screenshot(self) -> str:
        """Capture and save screenshot, return file path."""
        try:
            # Use the correct method name from VisionTool
            screenshot_b64 = self.vision.screenshot_to_base64()
            if screenshot_b64:
                # Save to file
                filepath = os.path.join(os.path.dirname(__file__), "live_view.png")
                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(screenshot_b64))
                return filepath
        except Exception as e:
            print(f"Screenshot error: {e}")
        return None
    
    def run_agent(self, message: str, history: list, model: str, planning_mode: bool):
        """Run the agent with the given message. Generator for live streaming."""
        if not message.strip():
            yield history, "", self.get_thought_stream(), None
            return
        
        # Update model if changed
        if model != self.agent.client.model:
            self.agent.client.model = model
        
        self.planning_mode = planning_mode
        self.is_running = True
        self.thought_log = []
        
        # Take initial screenshot of current state
        screenshot_path = self.capture_screenshot()
        
        # Add initial thought
        mode_name = "PLANNING" if planning_mode else "FAST"
        self.add_thought("thinking", f"Mode: {mode_name} | Task: {message[:50]}...")
        yield history, message, self.get_thought_stream(), screenshot_path
        
        # Build task prompt
        if planning_mode:
            task = f"Think step by step, then use ONE tool to complete: {message}"
            self.add_thought("plan", "Planning approach...")
        else:
            task = message
            self.add_thought("action", "Executing...")
        
        yield history, "", self.get_thought_stream(), screenshot_path
        
        # Collect response
        full_response = ""
        
        try:
            for update in self.agent.run(task):
                if update["type"] == "thought":
                    content = update["content"]
                    self.add_thought("thinking", content)
                    yield history, "", self.get_thought_stream(), screenshot_path
                    
                elif update["type"] == "response":
                    content = update["content"]
                    # For intermediate messages, append to history if verbose,
                    # but for now let's just update the last assistant message
                    # or keep it in full_response for the final complete event
                    full_response = content
                    self.add_thought("response", content[:150] + "...")
                    yield history, "", self.get_thought_stream(), screenshot_path
                    
                elif update["type"] == "tool_call":
                    tool = update["tool"]
                    args = update["args"]
                    self.add_thought("tool", f"Calling: {tool}({args})")
                    yield history, "", self.get_thought_stream(), screenshot_path
                    
                    # Take screenshot after visual tools
                    if tool in ["browser_navigate", "browser_click", "browser_type", 
                                "game_screenshot", "screenshot", "game_focus_window"]:
                        time.sleep(0.5)
                        screenshot_path = self.capture_screenshot() or screenshot_path
                        yield history, "", self.get_thought_stream(), screenshot_path
                        
                elif update["type"] == "tool_result":
                    result = update["result"]
                    result_preview = result[:150].replace("\n", " ")
                    self.add_thought("result", result_preview + "...")
                    
                    # Check for human takeover request
                    if "HUMAN_TAKEOVER_REQUESTED" in result:
                        reason = result.split("HUMAN_TAKEOVER_REQUESTED:")[-1].strip()
                        self.waiting_for_human = True
                        self.add_thought("pause", f"⏸️ WAITING FOR HUMAN: {reason}")
                        yield history, "", self.get_thought_stream(), screenshot_path
                        
                        # Wait for human to click continue
                        while self.waiting_for_human:
                            time.sleep(0.5)
                            screenshot_path = self.capture_screenshot() or screenshot_path
                            yield history, "", self.get_thought_stream(), screenshot_path
                        
                        self.add_thought("resume", "▶️ Human completed action, continuing...")
                    
                    # Take screenshot after tool completes
                    screenshot_path = self.capture_screenshot() or screenshot_path
                    yield history, "", self.get_thought_stream(), screenshot_path
                    
                elif update["type"] == "complete":
                    full_response = update["final_response"]
                    self.add_thought("complete", "Task completed!")
                    screenshot_path = self.capture_screenshot() or screenshot_path
                    yield history, "", self.get_thought_stream(), screenshot_path
                    
                elif update["type"] == "max_iterations":
                    self.add_thought("error", "Max iterations reached")
                    yield history, "", self.get_thought_stream(), screenshot_path
                    
        except Exception as e:
            self.add_thought("error", f"Error: {str(e)}")
            full_response = f"Error: {str(e)}"
            yield history, "", self.get_thought_stream(), screenshot_path
        
        self.is_running = False
        
        # Update history
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": full_response})
        
        yield history, "", self.get_thought_stream(), screenshot_path
    
    def clear_all(self):
        """Clear chat and thoughts."""
        self.agent.client.reset_conversation()
        self.thought_log = []
        return [], "", "Cleared. Ready for new task.", None


def create_pro_ui():
    """Create the Pro Gradio interface."""
    
    ui = ProAgentUI()
    
    # Get available models
    try:
        models = list_models()
    except:
        models = ["nemotron-3-nano:latest"]
    
    # Use Gradio's built-in dark theme
    theme = gr.themes.Base(
        primary_hue="cyan",
        secondary_hue="blue",
        neutral_hue="slate",
    ).set(
        body_background_fill="transparent",
        body_background_fill_dark="transparent",
        block_background_fill="rgba(10, 25, 50, 0.4)",
        block_background_fill_dark="rgba(10, 25, 50, 0.4)",
        input_background_fill="rgba(15, 35, 60, 0.95)",
        input_background_fill_dark="rgba(15, 35, 60, 0.95)",
        button_primary_background_fill="linear-gradient(135deg, #1a5a8a, #2a7aaa)",
        button_primary_background_fill_dark="linear-gradient(135deg, #1a5a8a, #2a7aaa)",
    )
    
    css = """
    html, body, .gradio-container {
        background: transparent !important;
    }
    #fractal-canvas {
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        z-index: -1;
        pointer-events: none;
    }
    .block, .form, .panel {
        background: rgba(10, 25, 50, 0.3) !important;
        border: 1px solid rgba(0, 255, 0, 0.2) !important;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.8) !important;
        border-radius: 12px !important;
    }
    .gradio-container, .main, .wrap {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    label, .label-wrap, .chatbot, .chatbot * {
        background: transparent !important;
        border: none !important;
    }
    *, *::before, *::after {
        color: #00ff00 !important;
        border-color: rgba(0, 255, 0, 0.3) !important;
    }
    .message, [class*="message"] {
        background: rgba(0, 30, 0, 0.4) !important;
        border: 1px solid rgba(0, 255, 0, 0.5) !important;
        border-radius: 8px !important;
    }
    textarea, input, .textbox, select {
        background: rgba(0, 20, 0, 0.6) !important;
        border: 1px solid #00ff00 !important;
        color: #00ff00 !important;
        font-family: 'Consolas', 'Monaco', monospace !important;
    }
    .gradio-textbox textarea, input[type="text"] {
        color: #ff8c00 !important;
    }
    button, .button, .btn {
        background: rgba(0, 80, 0, 0.3) !important;
        border: 1px solid #00ff00 !important;
        color: #00ff00 !important;
        transition: all 0.2s ease !important;
    }
    button:hover {
        background: rgba(0, 120, 0, 0.5) !important;
        box-shadow: 0 0 15px rgba(0, 255, 0, 0.4) !important;
    }
    input[type="checkbox"] {
        accent-color: #00ff00 !important;
        width: 20px !important;
        height: 20px !important;
        cursor: pointer !important;
    }
    input[type="checkbox"]:checked {
        background-color: #00ff00 !important;
        border: 2px solid #00ff00 !important;
        box-shadow: 0 0 10px #00ff00 !important;
    }
    .checkbox-label, label[data-testid="checkbox-label"] {
        font-weight: bold !important;
    }
    /* Hide audio player waveform */
    /* Hide audio player waveform */
    .gr-audio, [data-testid="waveform-slot"], .waveform-container, audio {
        display: none !important;
    }
    
    /* Hide Gradio API Footer */
    footer, .gradio-container > .main > .wrap > footer {
        display: none !important;
    }
    
    /* Toggle UI Button Fixed Position */
    #toggle-ui-btn {
        position: fixed !important;
        top: 20px !important;
        right: 20px !important;
        z-index: 99999 !important;
        width: auto !important;
        background: rgba(0, 50, 0, 0.6) !important;
        border: 1px solid #00ff00 !important;
        color: #00ff00 !important;
        backdrop-filter: blur(4px);
        opacity: 0 !important; /* Invisible by default */
        transition: opacity 0.3s ease-in-out !important;
    }
    #toggle-ui-btn:hover {
        opacity: 1 !important; /* Visible on hover */
    }
    
    /* Donate Button - Inline, visible with main UI */
    #donate-btn-inline:hover {
        background: rgba(80, 30, 80, 0.8) !important;
        box-shadow: 0 0 15px rgba(255, 105, 180, 0.4) !important;
        transform: scale(1.02);
    }
    
    /* Settings Button - Top Left, same hover-to-reveal behavior */
    #settings-btn {
        position: fixed !important;
        top: 20px !important;
        left: 20px !important;
        z-index: 99999 !important;
        width: 40px !important;
        min-width: 40px !important;
        height: 40px !important;
        padding: 0 !important;
        background: rgba(0, 50, 0, 0.6) !important;
        border: 1px solid #00ff00 !important;
        color: #00ff00 !important;
        backdrop-filter: blur(4px);
        opacity: 0 !important;
        transition: opacity 0.3s ease-in-out !important;
        font-size: 18px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    #settings-btn:hover {
        opacity: 1 !important;
    }
    
    /* Settings Panel - Collapsible with glassmorphism */
    #settings-panel {
        position: fixed !important;
        top: 70px !important;
        left: 20px !important;
        width: 320px !important;
        max-height: 80vh !important;
        overflow-y: auto !important;
        z-index: 99998 !important;
        background: rgba(10, 25, 50, 0.95) !important;
        border: 1px solid #00ff00 !important;
        border-radius: 12px !important;
        padding: 15px !important;
        backdrop-filter: blur(8px);
        display: none;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.8) !important;
    }
    #settings-panel.visible {
        display: block !important;
    }
    /* Hide the Gradio wrapper around the settings panel HTML */
    #settings-panel-wrapper {
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        margin: 0 !important;
        pointer-events: none;
    }
    #settings-panel-wrapper > * {
        pointer-events: auto;
    }
    #settings-panel h3 {
        margin-top: 0 !important;
        margin-bottom: 10px !important;
        border-bottom: 1px solid rgba(0, 255, 0, 0.3) !important;
        padding-bottom: 8px !important;
    }
    #settings-panel .settings-section {
        margin-bottom: 20px !important;
    }
    #settings-panel .settings-row {
        margin-bottom: 12px !important;
    }
    #settings-panel label {
        display: block !important;
        margin-bottom: 4px !important;
        font-size: 12px !important;
    }
    
    /* Slider styling for settings */
    #settings-panel input[type="range"] {
        width: 100% !important;
        height: 8px !important;
        background: rgba(0, 80, 0, 0.4) !important;
        border-radius: 4px !important;
        outline: none !important;
        -webkit-appearance: none !important;
    }
    #settings-panel input[type="range"]::-webkit-slider-thumb {
        -webkit-appearance: none !important;
        width: 16px !important;
        height: 16px !important;
        background: #00ff00 !important;
        border-radius: 50% !important;
        cursor: pointer !important;
        box-shadow: 0 0 8px #00ff00 !important;
    }
    #settings-panel input[type="range"]::-moz-range-thumb {
        width: 16px !important;
        height: 16px !important;
        background: #00ff00 !important;
        border-radius: 50% !important;
        cursor: pointer !important;
        box-shadow: 0 0 8px #00ff00 !important;
    }
    #settings-panel .slider-value {
        display: inline-block !important;
        min-width: 40px !important;
        text-align: right !important;
        font-family: monospace !important;
    }
    #settings-panel .config-display {
        background: rgba(0, 20, 0, 0.6) !important;
        padding: 8px !important;
        border-radius: 6px !important;
        font-family: monospace !important;
        font-size: 11px !important;
    }
    """
    
    with gr.Blocks(title="Pro AI Agent") as demo:
        # Toggle UI Button
        toggle_btn = gr.Button("Hide/Show UI", elem_id="toggle-ui-btn")
        
        toggle_js = """
        () => {
            const ui = document.getElementById('ui-container');
            const settingsPanel = document.getElementById('settings-panel');
            if (ui) {
                if (ui.style.opacity === '0') {
                     ui.style.opacity = '1';
                     ui.style.pointerEvents = 'auto';
                } else {
                     ui.style.opacity = '0';
                     ui.style.pointerEvents = 'none';
                     // Also hide settings panel when hiding UI
                     if (settingsPanel) settingsPanel.classList.remove('visible');
                }
            }
        }
        """
        
        toggle_btn.click(None, None, None, js=toggle_js)
        
        # Settings Button - Top Left
        settings_btn = gr.Button("⚙️", elem_id="settings-btn")
        
        # Settings Panel HTML - rendered via gr.HTML for custom layout
        settings_panel_html = gr.HTML(elem_id="settings-panel-wrapper", value="""
        <div id="settings-panel">
            <h3>⚙️ Settings</h3>
            
            <div class="settings-section">
                <h4 style="margin: 0 0 10px 0; font-size: 14px;">🌀 Fractal</h4>
                
                <div class="settings-row">
                    <label><input type="checkbox" id="fractal-enabled" checked> Enable Fractal</label>
                </div>
                
                <div class="settings-row">
                    <label>Morph Intensity: <span id="morph-value" class="slider-value">1.0</span></label>
                    <input type="range" id="morph-intensity" min="-10" max="10" step="0.5" value="1">
                </div>
                
                <div class="settings-row">
                    <label>Ripple Intensity: <span id="ripple-value" class="slider-value">1.0</span></label>
                    <input type="range" id="ripple-intensity" min="-10" max="10" step="0.5" value="1">
                </div>
                
                <div class="settings-row">
                    <label>Bass Zoom Intensity: <span id="bass-value" class="slider-value">1.0</span></label>
                    <input type="range" id="bass-intensity" min="-10" max="10" step="0.5" value="1">
                </div>
                
                <div class="settings-row">
                    <label>Config Values:</label>
                    <div class="config-display" id="config-display">
                        Zoom Rate: --<br>
                        Max Iter: --<br>
                        Morph Rate: --
                    </div>
                </div>
                
                <div class="settings-row">
                    <button id="refresh-effects-btn" style="width: 100%; padding: 8px; background: rgba(0, 80, 0, 0.4); border: 1px solid #00ff00; color: #00ff00; cursor: pointer; border-radius: 6px;">🔄 Refresh Effects</button>
                </div>
            </div>
            
            <div class="settings-section">
                <h4 style="margin: 0 0 10px 0; font-size: 14px;">🤖 LLM</h4>
                
                <div class="settings-row">
                    <label>System Prompt:</label>
                    <textarea id="system-prompt" style="width: 100%; height: 80px; background: rgba(0, 20, 0, 0.6); border: 1px solid #00ff00; color: #00ff00; font-family: monospace; font-size: 11px; resize: vertical; border-radius: 6px; padding: 6px;">You are an AI assistant that completes tasks by using tools.</textarea>
                </div>
                
                <div class="settings-row">
                    <label>Temperature: <span id="temp-value" class="slider-value">0.6</span></label>
                    <input type="range" id="temperature" min="0" max="2" step="0.1" value="0.6">
                </div>
                
                <div class="settings-row">
                    <label>Context Length: <span id="ctx-value" class="slider-value">2048</span></label>
                    <input type="range" id="context-length" min="512" max="8192" step="256" value="2048">
                </div>
                
                <div class="settings-row">
                    <button id="apply-llm-settings-btn" style="width: 100%; padding: 8px; background: rgba(0, 100, 50, 0.5); border: 1px solid #00ff00; color: #00ff00; cursor: pointer; border-radius: 6px;">✓ Apply LLM Settings</button>
                </div>
            </div>
        </div>
        """)
        
        # Settings panel toggle JavaScript
        settings_toggle_js = """
        () => {
            const panel = document.getElementById('settings-panel');
            if (panel) {
                panel.classList.toggle('visible');
            }
        }
        """
        settings_btn.click(None, None, None, js=settings_toggle_js)
        
        # Wrap EVERYTHING (Title + Main UI) in container for toggling
        with gr.Column(elem_id="ui-container") as main_wrapper:
            gr.Markdown("""
            <h1 style='text-align: center; margin-bottom: 0;'>Waterfall</h1>
            """)
            
            with gr.Row() as main_ui:
                # LEFT COLUMN: Chat + Thoughts
                with gr.Column(scale=1):
                    gr.Markdown("### Chat")
                    chatbot = gr.Chatbot(
                        label="Conversation",
                        height=300
                    )
                    
                    with gr.Row():
                        msg = gr.Textbox(
                            label="Message",
                            placeholder="Give me a task...",
                            scale=4,
                            lines=1
                        )
                        send_btn = gr.Button("Send", variant="primary", scale=1)
                    
                    with gr.Row():
                        planning_mode = gr.Checkbox(
                            label="Planning Mode",
                            value=False,
                            info="Think before acting"
                        )
                        continue_btn = gr.Button("Continue", variant="secondary")
                        clear_btn = gr.Button("Clear All")
                    
                    model_dropdown = gr.Dropdown(
                        choices=models,
                        value=DEFAULT_MODEL if DEFAULT_MODEL in models else (models[0] if models else "qwen2.5:14b"),
                        label="Model",
                        interactive=True
                    )
                    
                    gr.Markdown("### Thought Stream")
                    thought_display = gr.Textbox(
                        label="",
                        value="Waiting for input...",
                        lines=12,
                        max_lines=15,
                        interactive=False
                    )
            
                # RIGHT COLUMN: Live Visual Feed
                with gr.Column(scale=1):
                    gr.Markdown("### Live Visual Feed")
                    visual_feed = gr.Image(
                        label="What the AI sees/controls",
                        type="filepath",
                        height=500
                    )
                    
                    with gr.Row():
                        refresh_btn = gr.Button("Capture Screen")
                    
                    # Available Tools block removed
                    
                    gr.Markdown("### Music")
                    audio_player = gr.Audio(
                        label="Music Player",
                        type="filepath",
                        autoplay=True
                    )
                    next_btn = gr.Button("Next Track")
                    now_playing = gr.Textbox(
                        label="Now Playing",
                        value="Click 'Next Track' to start",
                        interactive=False,
                        lines=1
                    )
                    # Donate button - visible in main UI
                    gr.HTML("""
                    <a id="donate-btn-inline" href="https://venmo.com/code?user_id=2272974967144448513&created=1768270538" target="_blank" style="display: block; text-align: center; margin-top: 15px; padding: 10px 20px; background: rgba(50, 20, 50, 0.6); border: 1px solid #ff69b4; color: #ff69b4; text-decoration: none; border-radius: 8px; font-size: 14px; transition: all 0.3s ease;">
                        よろしければ 💝 Donate
                    </a>
                    """)
        
        # Event handlers
        def on_send(message, history, model, planning):
            yield from ui.run_agent(message, history, model, planning)
        
        def on_clear():
            return ui.clear_all()
        
        def on_refresh():
            return ui.capture_screenshot()
        
        def on_continue():
            """Signal agent to continue after human takeover."""
            ui.waiting_for_human = False
            ui.add_thought("resume", "Human clicked Continue - resuming agent...")
            return ui.get_thought_stream()
        
        # Music player logic
        import os
        import random
        music_folder = os.path.join(os.path.dirname(__file__), "Music")
        music_files = [f for f in os.listdir(music_folder) if f.endswith('.mp3')]
        random.shuffle(music_files)
        music_state = {"index": 0, "files": music_files}
        
        def on_next_track():
            if not music_state["files"]:
                return None, "No music files found"
            music_state["index"] = (music_state["index"] + 1) % len(music_state["files"])
            track = music_state["files"][music_state["index"]]
            track_path = os.path.join(music_folder, track)
            track_name = track.replace('.mp3', '')
            return track_path, track_name
        
        def on_audio_end():
            return on_next_track()
        
        # LLM Settings handlers - update the client when settings change
        def on_llm_settings_update(system_prompt_val, temperature_val, context_val):
            """Update LLM settings from the settings panel."""
            if system_prompt_val and system_prompt_val.strip():
                ui.agent.client.system_prompt = system_prompt_val
            if temperature_val is not None:
                ui.agent.client.temperature = float(temperature_val)
            if context_val is not None:
                ui.agent.client.num_predict = int(context_val)
            return f"Settings updated: temp={ui.agent.client.temperature}, ctx={ui.agent.client.num_predict}"
        
        # Hidden components for LLM settings bridge (updated via JavaScript)
        with gr.Row(visible=False):
            llm_system_prompt = gr.Textbox(elem_id="llm-system-prompt-hidden")
            llm_temperature = gr.Number(elem_id="llm-temperature-hidden", value=0.6)
            llm_context = gr.Number(elem_id="llm-context-hidden", value=2048)
            llm_settings_status = gr.Textbox()
        
        # Apply button for LLM settings (separate from HTML panel)
        apply_llm_btn = gr.Button("Apply LLM Settings", elem_id="apply-llm-btn", visible=False)
        
        send_btn.click(
            on_send,
            inputs=[msg, chatbot, model_dropdown, planning_mode],
            outputs=[chatbot, msg, thought_display, visual_feed]
        )
        msg.submit(
            on_send,
            inputs=[msg, chatbot, model_dropdown, planning_mode],
            outputs=[chatbot, msg, thought_display, visual_feed]
        )
        clear_btn.click(
            on_clear,
            outputs=[chatbot, msg, thought_display, visual_feed]
        )
        refresh_btn.click(
            on_refresh,
            outputs=[visual_feed]
        )
        continue_btn.click(
            on_continue,
            outputs=[thought_display]
        )
        next_btn.click(
            on_next_track,
            outputs=[audio_player, now_playing]
        )
        audio_player.stop(
            on_next_track,
            outputs=[audio_player, now_playing]
        )
        # LLM settings apply button handler
        apply_llm_btn.click(
            on_llm_settings_update,
            inputs=[llm_system_prompt, llm_temperature, llm_context],
            outputs=[llm_settings_status]
        )
        # Autoplay first track on load
        demo.load(
            on_next_track,
            outputs=[audio_player, now_playing]
        )
    
    return demo, theme, css


if __name__ == "__main__":
    demo, theme, css = create_pro_ui()
    js = """
    (function() {
        console.log("FRACTAL INITIALIZING...");
        const vertexShaderSource = `#version 300 es
            in vec2 a_position;
            void main() { gl_Position = vec4(a_position, 0.0, 1.0); }
        `;

        const glslFragmentCode = `#version 300 es
            precision highp float;
            uniform vec2 u_resolution;
            uniform float u_time;
            uniform vec2 u_fixX_h;    // Center X (high + low parts)
            uniform vec2 u_fixY_h;    // Center Y (high + low parts)
            uniform vec2 u_zoom;
            uniform vec2 u_invZoom;   // 1/zoom computed in JS with float64
            uniform float u_maxIter;
            uniform vec4 u_ripples[4];
            out vec4 fragColor;

            // ===== DOUBLE-SINGLE ARITHMETIC =====
            // Emulates ~48-bit mantissa for deep zoom precision
            vec2 ds_add(vec2 d1, vec2 d2) {
                float s = d1.x + d2.x;
                float t = (s - d1.x) - d2.x;
                float e = (d1.x - (s - t)) + (d2.x - t);
                float low = (d1.y + d2.y) + e;
                float high = s + low;
                return vec2(high, low + (s - high));
            }

            vec2 ds_sub(vec2 d1, vec2 d2) {
                return ds_add(d1, vec2(-d2.x, -d2.y));
            }

            vec2 ds_mul(vec2 d1, vec2 d2) {
                const float split = 4097.0;
                float c1 = d1.x * split;
                float h1 = c1 - (c1 - d1.x);
                float l1 = d1.x - h1;
                float c2 = d2.x * split;
                float h2 = c2 - (c2 - d2.x);
                float l2 = d2.x - h2;
                float p = d1.x * d2.x;
                float e = ((h1 * h2 - p) + h1 * l2 + l1 * h2) + l1 * l2;
                float s = p + (e + d1.x * d2.y + d1.y * d2.x);
                return vec2(s, (p - s) + (e + d1.x * d2.y + d1.y * d2.x));
            }

            vec3 palette(float t) {
                vec3 a = vec3(0.02, 0.01, 0.08);   
                vec3 b = vec3(0.15, 0.8, 1.0);   
                vec3 c = vec3(1.0, 1.0, 1.0);
                vec3 d = vec3(0.6, 0.4, 0.5); 
                return a + b * cos(6.28318 * (c * t + d));
            }

            void main() {
                vec2 uv = (gl_FragCoord.xy * 2.0 - u_resolution.xy) / u_resolution.y;
                
                // Use high-precision offset calculation
                vec2 offset_x = ds_mul(vec2(uv.x, 0.0), u_invZoom);
                vec2 offset_y = ds_mul(vec2(uv.y, 0.0), u_invZoom);
                
                // c = center + offset
                vec2 cx = ds_add(u_fixX_h, offset_x);
                vec2 cy = ds_add(u_fixY_h, offset_y);
                
                // ===== RESCALING FOR DEEP ZOOM =====
                // When values get too small, rescale to prevent underflow
                const float RESCALE_LOW = 1e-6;    // Rescale when below this
                const float RESCALE_HIGH = 1e6;    // Rescale when above this
                const float RESCALE_FACTOR = 1e6;  // Factor to rescale by
                
                // z starts at 0 for Mandelbrot
                vec2 zx = vec2(0.0);
                vec2 zy = vec2(0.0);
                float scaleFactor = 1.0;  // Cumulative scale
                
                float max_iter = u_maxIter;
                float smooth_iter = 0.0;
                float iter = 0.0;
                
                for (float i = 0.0; i < 2000.0; i++) {
                    if (i >= max_iter) break;
                    
                    // z = z^2 + c using double-single arithmetic
                    vec2 zx2 = ds_mul(zx, zx);
                    vec2 zy2 = ds_mul(zy, zy);
                    vec2 zxy = ds_mul(zx, zy);
                    
                    // Escape check using actual magnitude (with scale)
                    float mag2 = (zx2.x + zy2.x) * scaleFactor * scaleFactor;
                    if (mag2 > 256.0) {
                        float log_zn = log(mag2) / 2.0;
                        float nu = log(log_zn / log(2.0)) / log(2.0);
                        smooth_iter = i + 1.0 - nu;
                        break;
                    }
                    
                    // new_zx = zx^2 - zy^2 + cx
                    // new_zy = 2*zx*zy + cy
                    vec2 new_zx = ds_add(ds_sub(zx2, zy2), cx);
                    vec2 new_zy = ds_add(ds_add(zxy, zxy), cy);
                    
                    // RESCALING: If values get too small, rescale up
                    float newMag = abs(new_zx.x) + abs(new_zy.x);
                    if (newMag < RESCALE_LOW && newMag > 0.0) {
                        new_zx *= RESCALE_FACTOR;
                        new_zy *= RESCALE_FACTOR;
                        cx *= RESCALE_FACTOR;
                        cy *= RESCALE_FACTOR;
                        scaleFactor /= RESCALE_FACTOR;
                    } else if (newMag > RESCALE_HIGH) {
                        new_zx /= RESCALE_FACTOR;
                        new_zy /= RESCALE_FACTOR;
                        cx /= RESCALE_FACTOR;
                        cy /= RESCALE_FACTOR;
                        scaleFactor *= RESCALE_FACTOR;
                    }
                    
                    zx = new_zx;
                    zy = new_zy;
                    iter = i;
                }
                
                vec3 col;
                if (smooth_iter > 0.0) {
                    col = palette(smooth_iter * 0.02 + u_time * 0.02);
                    float glow = 1.0 / (smooth_iter * 0.03 + 0.5);
                    col += vec3(0.2, 0.1, 0.5) * glow;
                    
                    // Audio-reactive ripple effect
                    for (int r = 0; r < 4; r++) {
                        vec4 ripple = u_ripples[r];
                        if (ripple.y > 0.001) {
                            float wave = sin(smooth_iter * 0.3 + ripple.x * 8.0) * ripple.y;
                            col += vec3(0.1, 0.2, 0.3) * wave;
                        }
                    }
                } else {
                    float inner = iter / max_iter;
                    col = vec3(0.02, 0.01, 0.05) + vec3(0.02, 0.03, 0.08) * inner;
                }
                
                // Vignette
                vec2 vignetteUV = gl_FragCoord.xy / u_resolution.xy - 0.5;
                float vignette = 1.0 - dot(vignetteUV, vignetteUV) * 0.4;
                col *= vignette;
                
                fragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
            }
        `;

        function start() {
            if (document.getElementById('fractal-canvas')) return;
            const canvas = document.createElement('canvas');
            canvas.id = 'fractal-canvas';
            Object.assign(canvas.style, { position: 'fixed', top: '0', left: '0', width: '100vw', height: '100vh', zIndex: '-1', pointerEvents: 'none' });
            document.body.appendChild(canvas);
            
            const gl = canvas.getContext('webgl2', { preserveDrawingBuffer: true, antialias: false });
            if (!gl) return;

            function createShader(gl, type, source) {
                const s = gl.createShader(type);
                gl.shaderSource(s, source);
                gl.compileShader(s);
                if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
                    console.error("Shader Compile Error:", gl.getShaderInfoLog(s));
                    gl.deleteShader(s);
                    return null;
                }
                return s;
            }

            const program = gl.createProgram();
            console.log("DEBUG: Creating VS");
            const vs = createShader(gl, gl.VERTEX_SHADER, vertexShaderSource);
            console.log("DEBUG: Creating FS");
            const fs = createShader(gl, gl.FRAGMENT_SHADER, glslFragmentCode);
            if (!vs || !fs) { console.error("DEBUG: Shader creation failed"); return; }
            
            console.log("DEBUG: Attaching shaders");
            gl.attachShader(program, vs);
            gl.attachShader(program, fs);
            gl.linkProgram(program);
            
            if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
                 console.error("Program Link Error:", gl.getProgramInfoLog(program));
                 return;
            }
            console.log("DEBUG: Link success, using program");
            gl.useProgram(program);

            const locRes = gl.getUniformLocation(program, "u_resolution");
            const locTime = gl.getUniformLocation(program, "u_time");
            const locFXH = gl.getUniformLocation(program, "u_fixX_h");
            const locFYH = gl.getUniformLocation(program, "u_fixY_h");
            const locZoom = gl.getUniformLocation(program, "u_zoom");
            const locInvZoom = gl.getUniformLocation(program, "u_invZoom");
            const locMaxIter = gl.getUniformLocation(program, "u_maxIter");
            // Multi-ripple uniform locations
            const locRipples = [
                gl.getUniformLocation(program, "u_ripples[0]"),
                gl.getUniformLocation(program, "u_ripples[1]"),
                gl.getUniformLocation(program, "u_ripples[2]"),
                gl.getUniformLocation(program, "u_ripples[3]")
            ];

            const buffer = gl.createBuffer();
            gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
            gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
            const pos = gl.getAttribLocation(program, "a_position");
            gl.enableVertexAttribArray(pos);
            gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);

            // ===== CONFIGURABLE PARAMETERS =====
            // These can be tuned via fractal_config.json
            let cfg = {
                zoom: { rate: 0.03, minLog: 0, maxLog: 10, deadspaceThresholdSeconds: 0.5, reverseSlowdown: 0.95, minZoomOutDistance: 2.5 },
                iteration: { baseCount: 300, maxCount: 1000, logMultiplier: 60 },
                animation: { morphRate: 0.12, powerBase: 1.2, powerRange: 0.2, panRadius: 0.01, panSpeed: 0.15 },
                steering: { smoothing: 0.97, strength: 0.015, probeRadius: 0.25, gradientThreshold: 0.05, probeIterations: 250, searchRadiusMultiplier: 4.0 },
                traps: { circleRadiusBase: 0.5, circleRadiusRange: 0.3, circleSpeed: 0.2, pointDistance: 0.3, pointSpeedX: 0.15, pointSpeedY: 0.18, lineSpeed: 0.1 }
            };
            
            // Load config from file (async, non-blocking)
            fetch('/file=fractal_config.json').then(r => r.json()).then(c => { cfg = {...cfg, ...c}; console.log('Fractal config loaded:', cfg); updateConfigDisplay(); }).catch(() => console.log('Using default fractal config'));

            // ===== SETTINGS PANEL INTEGRATION =====
            // Global settings controlled by the settings panel
            window.fractalSettings = {
                enabled: true,
                morphIntensity: 1.0,
                rippleIntensity: 1.0,
                bassZoomIntensity: 1.0
            };
            
            // Update config display in settings panel
            function updateConfigDisplay() {
                const display = document.getElementById('config-display');
                if (display && cfg) {
                    display.innerHTML = `Zoom Rate: ${cfg.zoom?.rate?.toFixed(3) || '--'}<br>Max Iter: ${cfg.iteration?.maxCount || '--'}<br>Morph Rate: ${cfg.animation?.morphRate?.toFixed(3) || '--'}`;
                }
            }
            
            // Setup settings panel event listeners
            function setupSettingsHandlers() {
                // Fractal enable/disable toggle
                const fractalToggle = document.getElementById('fractal-enabled');
                if (fractalToggle) {
                    fractalToggle.addEventListener('change', (e) => {
                        window.fractalSettings.enabled = e.target.checked;
                        console.log('Fractal enabled:', window.fractalSettings.enabled);
                    });
                }
                
                // Morph intensity slider
                const morphSlider = document.getElementById('morph-intensity');
                const morphValue = document.getElementById('morph-value');
                if (morphSlider) {
                    morphSlider.addEventListener('input', (e) => {
                        window.fractalSettings.morphIntensity = parseFloat(e.target.value);
                        if (morphValue) morphValue.textContent = parseFloat(e.target.value).toFixed(1);
                    });
                }
                
                // Ripple intensity slider
                const rippleSlider = document.getElementById('ripple-intensity');
                const rippleValue = document.getElementById('ripple-value');
                if (rippleSlider) {
                    rippleSlider.addEventListener('input', (e) => {
                        window.fractalSettings.rippleIntensity = parseFloat(e.target.value);
                        if (rippleValue) rippleValue.textContent = parseFloat(e.target.value).toFixed(1);
                    });
                }
                
                // Bass zoom intensity slider
                const bassSlider = document.getElementById('bass-intensity');
                const bassValue = document.getElementById('bass-value');
                if (bassSlider) {
                    bassSlider.addEventListener('input', (e) => {
                        window.fractalSettings.bassZoomIntensity = parseFloat(e.target.value);
                        if (bassValue) bassValue.textContent = parseFloat(e.target.value).toFixed(1);
                    });
                }
                
                // Temperature slider (LLM)
                const tempSlider = document.getElementById('temperature');
                const tempValue = document.getElementById('temp-value');
                if (tempSlider) {
                    tempSlider.addEventListener('input', (e) => {
                        window.llmSettings = window.llmSettings || {};
                        window.llmSettings.temperature = parseFloat(e.target.value);
                        if (tempValue) tempValue.textContent = parseFloat(e.target.value).toFixed(1);
                    });
                }
                
                // Context length slider (LLM)
                const ctxSlider = document.getElementById('context-length');
                const ctxValue = document.getElementById('ctx-value');
                if (ctxSlider) {
                    ctxSlider.addEventListener('input', (e) => {
                        window.llmSettings = window.llmSettings || {};
                        window.llmSettings.contextLength = parseInt(e.target.value);
                        if (ctxValue) ctxValue.textContent = e.target.value;
                    });
                }
                
                // Refresh effects button - uses global function
                const refreshBtn = document.getElementById('refresh-effects-btn');
                if (refreshBtn) {
                    refreshBtn.addEventListener('click', () => {
                        window.refreshFractalEffects();
                        // Visual feedback
                        refreshBtn.textContent = '✓ Refreshed!';
                        setTimeout(() => { refreshBtn.textContent = '🔄 Refresh Effects'; }, 1500);
                    });
                    console.log('Refresh button handler attached');
                } else {
                    console.warn('Refresh button not found in DOM');
                }
                
                // Apply LLM Settings button - syncs to hidden Gradio components
                const applyLLMBtn = document.getElementById('apply-llm-settings-btn');
                if (applyLLMBtn) {
                    applyLLMBtn.addEventListener('click', () => {
                        console.log('Applying LLM settings...');
                        const systemPrompt = document.getElementById('system-prompt')?.value || '';
                        const temperature = parseFloat(document.getElementById('temperature')?.value || 0.6);
                        const contextLength = parseInt(document.getElementById('context-length')?.value || 2048);
                        
                        // Store in window for Python to read via custom event
                        window.llmSettings = { systemPrompt, temperature, contextLength };
                        
                        // Find hidden Gradio components and update them
                        const hiddenPrompt = document.querySelector('#llm-system-prompt-hidden textarea');
                        const hiddenTemp = document.querySelector('#llm-temperature-hidden input');
                        const hiddenCtx = document.querySelector('#llm-context-hidden input');
                        
                        if (hiddenPrompt) {
                            hiddenPrompt.value = systemPrompt;
                            hiddenPrompt.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                        if (hiddenTemp) {
                            hiddenTemp.value = temperature;
                            hiddenTemp.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                        if (hiddenCtx) {
                            hiddenCtx.value = contextLength;
                            hiddenCtx.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                        
                        // Click the hidden apply button to trigger Python handler
                        const applyBtn = document.querySelector('#apply-llm-btn');
                        if (applyBtn) applyBtn.click();
                        
                        // Visual feedback
                        applyLLMBtn.textContent = '✓ Applied!';
                        setTimeout(() => { applyLLMBtn.textContent = '✓ Apply LLM Settings'; }, 1500);
                    });
                }
                
                updateConfigDisplay();
            }
            
            // ===== GLOBAL REFRESH FUNCTION =====
            // Can be called from button or automatically
            window.refreshFractalEffects = function() {
                console.log('=== REFRESH FRACTAL EFFECTS ===');
                
                // Reset all ripple state
                window.ripples = [];
                window.avgBeatDelta = 0.01;
                window.lastBeatEnergy = 0;
                window.globalAudioTime = 0;
                console.log('Ripple state reset');
                
                // Force audio re-initialization by resetting isAudioActive
                // This triggers the polling loop to re-establish the connection
                isAudioActive = false;
                console.log('Audio connection will be re-established on next poll');
                
                // Resume audio context if suspended
                if (window.audioCtx && window.audioCtx.state === 'suspended') {
                    window.audioCtx.resume();
                    console.log('Audio context resumed');
                }
                
                // Reload config
                fetch('/file=fractal_config.json')
                    .then(r => r.json())
                    .then(c => { 
                        cfg = {...cfg, ...c}; 
                        console.log('Config reloaded:', cfg); 
                        updateConfigDisplay(); 
                    })
                    .catch(() => console.log('Config reload skipped'));
            };
            
            // ===== AUTOMATIC 4-MINUTE RESET =====
            // Prevents floating-point precision issues during long songs
            const RESET_INTERVAL_MS = 4 * 60 * 1000; // 4 minutes
            setInterval(() => {
                console.log('Auto-reset triggered (4 min interval)');
                window.refreshFractalEffects();
            }, RESET_INTERVAL_MS);
            
            // Delayed setup to ensure DOM is ready - retry multiple times
            function attemptSetup(retries) {
                const refreshBtn = document.getElementById('refresh-effects-btn');
                if (refreshBtn) {
                    console.log('Settings handlers setup successful');
                    setupSettingsHandlers();
                } else if (retries > 0) {
                    console.log('Waiting for settings panel DOM...', retries);
                    setTimeout(() => attemptSetup(retries - 1), 500);
                } else {
                    console.warn('Settings panel not found after retries');
                }
            }
            setTimeout(() => attemptSetup(10), 1000);

            const startTime = Date.now();
            let currentZoomLog = 0;
            let actualZoomRate = cfg.zoom.rate;
            
            // ========== MANDELBROT - MISIUREWICZ POINT INFINITE ZOOM ==========
            // "Seahorse Valley" spiral point - perfect self-similarity!
            const TARGET_X = -0.743643887037158704752191506114774;
            const TARGET_Y = 0.131825904205311970493132056385139;
            const MAX_ZOOM_LOG = 12;  // Reset at ~163,000x zoom (DS precision limit)
            
            // Camera locked to Misiurewicz point
            let centerX = TARGET_X;
            let centerY = TARGET_Y;
            
            // Smooth transitions
            let smoothPauseFactor = 1.0;
            let smoothZoomRate = cfg.zoom.rate;

            function splitDouble(d) {
                const hi = Math.fround(d);
                const lo = d - hi;
                return [hi, lo];
            }

            let lastFrameTime = performance.now();
            let smoothedDelta = 0.0166;
            let accumulatedTime = 0;
            let accumulatedZoomLog = 0;

            // Ripple State - MULTI-RIPPLE SYSTEM (on window for settings access)
            // Each beat spawns a new ripple wave with its own birth time
            const MAX_RIPPLES = 6;  // Number of concurrent ripple waves
            window.ripples = [];  // Array of {birthTime, intensity, type} objects
            window.lastBeatEnergy = 0;
            window.avgBeatDelta = 0.01; // Adaptive threshold baseline
            window.globalAudioTime = 0;  // Cumulative audio-synced time
            // Local aliases for convenience
            let ripples = window.ripples;
            let lastBeatEnergy = window.lastBeatEnergy;
            let avgBeatDelta = window.avgBeatDelta;
            let globalAudioTime = window.globalAudioTime;
            
            // Sync Cleanup State
            let activeSyncInterval = null;
            let activeCleanupListeners = null;

            // ===== AUDIO SYNC SETUP =====
            let audioCtx, analyser, source;
            let audioDataArray;
            let isAudioActive = false;
            let bassEnergy = 0;
            let midEnergy = 0;
            let highEnergy = 0;

            function setupAudio() {
                // Audio Context Global
                window.audioCtx = null;
                
                // Debug overlay REMOVED for production
                /* 
                if (!window.audioDebug) { ... }
                */
                window.audioDebug = null; 


                // Helper: Recursive Shadow DOM Search
                function findDeepAudio(root) {
                    let audios = Array.from(root.querySelectorAll('audio'));
                    const all = root.querySelectorAll('*');
                    for (const el of all) {
                        if (el.shadowRoot) {
                            audios = audios.concat(findDeepAudio(el.shadowRoot));
                        }
                    }
                    return audios;
                }

                // POLLING LOOP: Check every 500ms
                const pollInterval = setInterval(() => {
                    if (isAudioActive) {
                        if (window.audioCtx && window.audioCtx.state === 'suspended') window.audioCtx.resume();
                        return;
                    }

                    // Deep scan for ALL audio elements (Light + Shadow DOM)
                    const audioEls = findDeepAudio(document);
                    
                    if (audioEls.length === 0) {
                        if (window.audioDebug) window.audioDebug.innerText = "Status: Searching DOM for <audio>...";
                        return;
                    }

                    // Find the one that is actively playing
                    let activeEl = null;
                    for (const el of audioEls) {
                        if (!el.paused && el.currentTime > 0) {
                            activeEl = el;
                            break;
                        }
                    }

                    if (!activeEl) {
                        // Debug info for the first few elements found
                        const count = audioEls.length;
                        const first = audioEls[0];
                        const sName = first.src ? first.src.split('/').pop().substring(0, 10) : "NoSrc";
                        const debugInfo = `Found ${count}. 1st: P:${first.paused} T:${first.currentTime.toFixed(1)}`;
                        if (window.audioDebug) window.audioDebug.innerText = `Status: Waiting... ${debugInfo}`;
                        return;
                    }
                    
                    const audioEl = activeEl;

                    // FOUND PLAYING ELEMENT!
                    console.log("AUDIO STARTED! Hooking up visualizer...");
                    if (window.audioDebug) window.audioDebug.innerText = "Status: Play Detected! Starting Fetch...";

                    // Stop polling? No, keep it running to resume context if needed, but shield init logic
                    // Actually, let's set isAudioActive=true *inside* the success block

                    // INIT LOGIC
                    try {
                        const AudioContext = window.AudioContext || window.webkitAudioContext;
                        audioCtx = new AudioContext();
                        window.audioCtx = audioCtx; // Global ref

                        analyser = audioCtx.createAnalyser();
                        analyser.fftSize = 2048;
                        const bufferLength = analyser.frequencyBinCount;
                        audioDataArray = new Uint8Array(bufferLength);
                        
                        // Anti-optimization Gain
                        const gainNode = audioCtx.createGain();
                        gainNode.gain.value = 0.001; 
                        analyser.connect(gainNode);
                        gainNode.connect(audioCtx.destination);
                        
                        // Resume on click (backup)
                        document.body.addEventListener('click', () => {
                            if (audioCtx.state === 'suspended') audioCtx.resume();
                        });

                        // Strategy Choice
                        const src = audioEl.currentSrc || audioEl.src;
                        
                        // 1. Stream
                        if (audioEl.srcObject) {
                            console.log("Strategy: MediaStream");
                            if (window.audioDebug) window.audioDebug.innerText = "Status: Stream Source...";
                            const source = audioCtx.createMediaStreamSource(audioEl.srcObject);
                            source.connect(analyser);
                            isAudioActive = true;
                            // Clear polling? Nah, safe to keep checking 
                            return;
                        }

                        // 2. Fetch & Decode
                        if (src) {
                            console.log("Strategy: Fetch & Decode", src);
                            if (window.audioDebug) window.audioDebug.innerText = "Status: Downloading...";
                            
                            // Mark active so we don't retry fetch
                            isAudioActive = true; 

                            fetch(src)
                                .then(r => r.arrayBuffer())
                                .then(b => audioCtx.decodeAudioData(b))
                                .then(audioBuffer => {
                                    // Peak Check
                                    const raw = audioBuffer.getChannelData(0);
                                    let peak = 0;
                                    for(let i=0; i<raw.length; i+=100) {
                                        const v = Math.abs(raw[i]);
                                        if(v > peak) peak = v;
                                    }
                                    if (window.audioDebug) window.audioDebug.innerText = `Status: Decoded! Peak: ${peak.toFixed(4)}`;
                                    
                                    startBufferSync(audioBuffer, audioEl);
                                })
                                .catch(e => {
                                    console.error("Fetch Error:", e);
                                    isAudioActive = false; // Allow retry
                                    if (window.audioDebug) window.audioDebug.innerText = "Error: " + e.message;
                                });
                        }

                    } catch(e) {
                         console.error("Init Error:", e);
                         if (window.audioDebug) window.audioDebug.innerText = "Init Fail: " + e.message;
                    }

                }, 500); // End Interval

                // Helper: Sync Buffer Logic
                function startBufferSync(decodedBuffer, element) {
                     let bufferSource = null;
                     let lastSyncTime = 0;
                     let lastCtxTime = 0;
                     
                     function playBuffer(startTime) {
                         if (bufferSource) try { bufferSource.stop(); } catch(e){}
                         bufferSource = audioCtx.createBufferSource();
                         bufferSource.buffer = decodedBuffer;
                         bufferSource.connect(analyser); // Connect to analyser
                         
                         let offset = startTime;
                         if (offset >= decodedBuffer.duration) offset = 0;
                         
                         bufferSource.start(0, offset);
                         lastSyncTime = offset;
                         lastCtxTime = audioCtx.currentTime;
                         
                         bufferSource.onended = () => { /* clean */ };
                     }
                     
                     function stopBuffer() {
                        if (bufferSource) { try { bufferSource.stop(); } catch(e){} bufferSource = null; }
                     }
                     
                     // Sync Interval (runs inside the closure)
                     // CLEANUP OLD INTERVAL
                     if (activeSyncInterval) clearInterval(activeSyncInterval);
                     if (activeCleanupListeners) activeCleanupListeners();

                     activeSyncInterval = setInterval(() => {
                        if (!element.paused) {
                            if (!bufferSource) playBuffer(element.currentTime);
                            else {
                                // Drift Correction - TIGHTER SYNC
                                const currentBufferTime = lastSyncTime + (audioCtx.currentTime - lastCtxTime);
                                // If drift > 0.05s, resync
                                if (Math.abs(element.currentTime - currentBufferTime) > 0.05) {
                                    playBuffer(element.currentTime);
                                }
                            }
                        } else {
                            if (bufferSource) stopBuffer();
                        }
                     }, 100); 
                     
                     // Event Handlers
                     const onSeek = () => { if(!element.paused) playBuffer(element.currentTime); };
                     const onPause = stopBuffer;
                     const onPlay = () => {
                        playBuffer(element.currentTime);
                        // Reset stats using window scope
                        window.avgBeatDelta = 0.01;
                        window.lastBeatEnergy = 0;
                        window.globalAudioTime = 0;
                        window.ripples = [];
                     };
                     const onLoaded = () => {
                        window.avgBeatDelta = 0.01;
                        window.lastBeatEnergy = 0;
                        window.globalAudioTime = 0;
                        window.ripples = [];
                        console.log("New Track Loaded - Ripple Stats Reset");
                     };

                     element.addEventListener('seeking', onSeek);
                     element.addEventListener('pause', onPause);
                     element.addEventListener('play', onPlay);
                     element.addEventListener('loadeddata', onLoaded);
                     
                     // Store cleanup function
                     activeCleanupListeners = () => {
                         element.removeEventListener('seeking', onSeek);
                         element.removeEventListener('pause', onPause);
                         element.removeEventListener('play', onPlay);
                         element.removeEventListener('loadeddata', onLoaded);
                         if (bufferSource) stopBuffer();
                     };
                }
            }
            
            // Start immediately
            setupAudio();

            function render(now) {
                // Check if fractal is disabled via settings
                if (!window.fractalSettings?.enabled) {
                    requestAnimationFrame(render);
                    return;
                }
                
                // Calculate actual delta time
                const dt = (now - lastFrameTime) * 0.001;
                lastFrameTime = now;
                
                // Temporal smoothing of delta-time (90/10 blend)
                // This prevents micro-stutters from browser scheduling issues
                if (dt > 0 && dt < 0.1) { // Sanity check to avoid jumps after tab switch
                    smoothedDelta = smoothedDelta * 0.9 + dt * 0.1;
                }

                // Increment time accumulator based on SMOOTHED delta
                
                // ===== AUDIO ANALYSIS =====
                let audioZoomBoost = 0;
                let audioMorphBoost = 1.0;
                
                if (isAudioActive && audioDataArray) {
                    analyser.getByteFrequencyData(audioDataArray);
                    
                    // Calculate energy bands
                    const bassRange = audioDataArray.slice(0, 10);   // ~0-200Hz
                    const midRange = audioDataArray.slice(10, 100);  // ~200-2000Hz
                    const highRange = audioDataArray.slice(100, 512); // ~2kHz+
                    
                    // Normalize to 0-1
                    bassEnergy = bassRange.reduce((a, b) => a + b, 0) / bassRange.length / 255.0;
                    midEnergy = midRange.reduce((a, b) => a + b, 0) / midRange.length / 255.0;
                    highEnergy = highRange.reduce((a, b) => a + b, 0) / highRange.length / 255.0;
                    
                    // Sync local variables with window scope (in case refresh was clicked)
                    ripples = window.ripples;
                    lastBeatEnergy = window.lastBeatEnergy;
                    avgBeatDelta = window.avgBeatDelta;
                    globalAudioTime = window.globalAudioTime;
                    
                    // TRANSIENT DETECTION (Ripple)
                    const beatEnergy = Math.max(bassEnergy, midEnergy);
                    const beatDelta = beatEnergy - lastBeatEnergy;
                    
                    // Separate Deltas for Type Detection
                    // We need these to know IF it was a kick or a snare
                    // (Note: We still use max energy for the trigger threshold to keep it unified)
                    // But we could strictly calculate previous frame state if we really wanted precision.
                    // For now, simple comparison of current energy levels usually works because hits are distinct.
                    // Actually, let's look at which one DROVE the beatDelta.
                    
                    // Adaptive Average Tracking - DECAY FIX
                    const activity = Math.max(0, beatDelta);
                    avgBeatDelta = avgBeatDelta * 0.95 + activity * 0.05;
                    
                    // SAFETY CLAMP: Prevent threshold from running away on loud tracks
                    if (avgBeatDelta > 0.1) avgBeatDelta = 0.1;
                    
                    // Dynamic Trigger
                    const dynamicThreshold = Math.max(0.005, avgBeatDelta * 1.5);
                    
                    if (beatDelta > dynamicThreshold && beatEnergy > 0.1) { 
                         // PERCUSSION HIT! Spawn a new ripple wave
                         const rippleType = bassEnergy > midEnergy ? 'bass' : 'mid';
                         const intensity = rippleType === 'bass' ? 0.12 : 0.06;
                         
                         // Add new ripple to pool
                         window.ripples.push({
                             birthTime: globalAudioTime,
                             intensity: intensity,
                             type: rippleType
                         });
                         
                         // Keep pool size limited - remove oldest when full
                         while (window.ripples.length > MAX_RIPPLES) {
                             window.ripples.shift();
                         }
                    }
                    lastBeatEnergy = beatEnergy;
                    window.lastBeatEnergy = lastBeatEnergy;
                    
                    // Advance global audio time
                    globalAudioTime += smoothedDelta;
                    window.globalAudioTime = globalAudioTime;
                    
                    // NaN SAFETY GUARD
                    if (isNaN(globalAudioTime)) {
                        globalAudioTime = 0;
                        window.globalAudioTime = 0;
                    }
                    if (isNaN(avgBeatDelta)) {
                        avgBeatDelta = 0.01;
                        window.avgBeatDelta = 0.01;
                    }
                    
                    // Update ripple intensities with decay and remove dead ripples
                    window.ripples = window.ripples.filter(r => {
                        r.intensity *= 0.96;  // Slightly slower decay for sustained waves
                        return r.intensity > 0.005;  // Remove when too faint
                    });
                    
                    // AUDIO CONTEXT WATCHDOG
                    // Ensure it didn't get suspended
                     if (window.audioCtx && window.audioCtx.state === 'suspended') {
                         window.audioCtx.resume();
                     }
                    
                    // Apply effects
                    // Bass thumps the zoom - INSTANT response (no smoothing)
                    // Lower threshold (0.2) + High multiplier (0.8) for observable "punch"
                    if (bassEnergy > 0.2) {
                        audioZoomBoost = (bassEnergy - 0.2) * 0.8; 
                    }
                    
                    // Mids/Highs speed up morphing
                    // High multiplier (8.0) to make the shape dance noticeably
                    audioMorphBoost = 1.0 + (midEnergy + highEnergy) * 8.0;
                    
                    // Update Debug Text - REMOVED for final polish
                    /*
                    if (window.audioDebug) {
                         // ... debug code removed for clean view ...
                         if (window.audioDebug.parentNode) window.audioDebug.parentNode.removeChild(window.audioDebug);
                         window.audioDebug = null;
                    }
                    */
                }
                
                // Apply settings intensity multipliers
                const morphMultiplier = window.fractalSettings?.morphIntensity ?? 1.0;
                const bassMultiplier = window.fractalSettings?.bassZoomIntensity ?? 1.0;
                
                accumulatedTime += smoothedDelta * (1.0 + (audioMorphBoost - 1.0) * morphMultiplier);
                // NOTE: Zoom accumulation is now handled by the adaptive zoom pause system below

                const dpr = window.devicePixelRatio || 1;
                const qualityScale = 0.75;  // Balance between quality and performance (0.5-1.0)
                const MAX_W = 2560;
                const MAX_H = 1440;
                let targetW = Math.floor(canvas.clientWidth * dpr * qualityScale);
                let targetH = Math.floor(canvas.clientHeight * dpr * qualityScale);
                if (targetW > MAX_W) { targetH = Math.floor(targetH * (MAX_W / targetW)); targetW = MAX_W; }
                if (targetH > MAX_H) { targetW = Math.floor(targetW * (MAX_H / targetH)); targetH = MAX_H; }
                
                if (canvas.width !== targetW || canvas.height !== targetH) {
                    canvas.width = targetW;
                    canvas.height = targetH;
                    gl.viewport(0, 0, canvas.width, canvas.height);
                }

                // ========== MANDELBROT INFINITE ZOOM ==========
                // Camera locked to Misiurewicz point - no boundary seeking needed!
                // Always zoom in, seamless reset at precision limit
                
                // Calculate zoom
                const zoom = Math.exp(accumulatedZoomLog);
                
                // Zoom rate (audio-reactive)
                let effectiveZoomRate = cfg.zoom.rate;
                if (isAudioActive && audioZoomBoost > 0) {
                    effectiveZoomRate += audioZoomBoost * bassMultiplier;
                }
                
                // Always zoom in
                accumulatedZoomLog += effectiveZoomRate * smoothedDelta;
                // No reset needed - shader rescaling handles infinite precision
                
                // Dynamic max iterations - sync with zoom log
                let gpuMaxIter = cfg.iteration.baseCount + cfg.iteration.logMultiplier * accumulatedZoomLog;
                if (gpuMaxIter > 4000) gpuMaxIter = 4000;

                gl.uniform2f(locRes, canvas.width, canvas.height);
                gl.uniform1f(locTime, accumulatedTime);
                gl.uniform2fv(locFXH, splitDouble(centerX));
                gl.uniform2fv(locFYH, splitDouble(centerY));
                gl.uniform2fv(locZoom, splitDouble(zoom));
                gl.uniform2fv(locInvZoom, splitDouble(1.0 / zoom));
                gl.uniform1f(locMaxIter, gpuMaxIter);
                
                // Populate ripple uniforms with top 4 ripples (sorted by intensity)
                const rippleMultiplier = window.fractalSettings?.rippleIntensity ?? 1.0;
                const sortedRipples = [...window.ripples].sort((a, b) => b.intensity - a.intensity).slice(0, 4);
                for (let i = 0; i < 4; i++) {
                    if (i < sortedRipples.length) {
                        const r = sortedRipples[i];
                        const timeSinceBirth = globalAudioTime - r.birthTime;
                        gl.uniform4f(locRipples[i], timeSinceBirth, r.intensity * rippleMultiplier, 0.0, 0.0);
                    } else {
                        gl.uniform4f(locRipples[i], 0.0, 0.0, 0.0, 0.0);  // Empty slot
                    }
                }

                gl.drawArrays(gl.TRIANGLES, 0, 6);
                requestAnimationFrame(render);
            }
            requestAnimationFrame((t) => {
                lastFrameTime = t;
                requestAnimationFrame(render);
            });
            console.log("FRACTAL RUNNING");
        }

        const attempt = () => {
            if (document.body) { start(); }
            else { setTimeout(attempt, 500); }
        };
        attempt();
    })();
    """
    import os
    music_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "Music"))
    config_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "fractal_config.json"))
    app_dir = os.path.normpath(os.path.dirname(__file__))
    demo.launch(share=False, server_name="127.0.0.1", server_port=7860, theme=theme, css=css, js=js, allowed_paths=[music_dir, config_path, app_dir])

