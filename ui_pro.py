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
    """
    
    with gr.Blocks(title="Pro AI Agent") as demo:
        # Toggle UI Button
        toggle_btn = gr.Button("Hide/Show UI", elem_id="toggle-ui-btn")
        
        toggle_js = """
        () => {
            const ui = document.getElementById('ui-container');
            if (ui) {
                if (ui.style.opacity === '0') {
                     ui.style.opacity = '1';
                     ui.style.pointerEvents = 'auto';
                } else {
                     ui.style.opacity = '0';
                     ui.style.pointerEvents = 'none';
                }
            }
        }
        """
        
        toggle_btn.click(None, None, None, js=toggle_js)
        
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
            uniform vec2 u_fixX_h;
            uniform vec2 u_fixY_h;
            uniform vec2 u_zoom;
            uniform vec2 u_invZoom;  // 1/zoom computed in JS (float64) for deep zoom precision
            uniform float u_maxIter;
            // Multi-ripple system: up to 4 concurrent ripples
            // Each vec4: x=timeSinceBirth, y=intensity, z=unused, w=unused
            uniform vec4 u_ripples[4];
            out vec4 fragColor;

            // Double-single arithmetic for deep zoom precision
            vec2 ds_add(vec2 d1, vec2 d2) {
                float s = d1.x + d2.x;
                float t = (s - d1.x) - d2.x;
                float e = (d1.x - (s - t)) + (d2.x - t);
                float low = (d1.y + d2.y) + e;
                float high = s + low;
                return vec2(high, low + (s - high));
            }
            vec2 ds_sub(vec2 d1, vec2 d2) { return ds_add(d1, vec2(-d2.x, -d2.y)); }
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

            // Procedural noise functions for texture overlay
            float hash(vec2 p) {
                return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
            }
            float noise(vec2 p) {
                vec2 i = floor(p);
                vec2 f = fract(p);
                f = f * f * (3.0 - 2.0 * f);
                return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x),
                           mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
            }
            float fbm(vec2 p) {
                float v = 0.0, a = 0.5;
                mat2 rot = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.5));
                for (int i = 0; i < 5; i++) {
                    v += a * noise(p);
                    p = rot * p * 2.0;
                    a *= 0.5;
                }
                return v;
            }

            // UNDERTALE WATERFALL PALETTE - Matches reference image
            vec3 palette(float t, float time) {
                // Primary: Very deep navy/indigo (almost black)
                vec3 a1 = vec3(0.02, 0.02, 0.08);      // Near-black navy
                vec3 b1 = vec3(0.05, 0.15, 0.35);     // Subtle blue range
                vec3 c1 = vec3(1.0, 1.0, 1.0);
                vec3 d1 = vec3(0.5, 0.6, 0.7);
                vec3 col1 = a1 + b1 * cos(6.28318 * (c1 * t + d1));
                
                // Secondary: Bright cyan/turquoise water glow
                vec3 a2 = vec3(0.0, 0.3, 0.5);        // Cyan base
                vec3 b2 = vec3(0.0, 0.6, 0.7);        // Bright cyan range
                vec3 c2 = vec3(0.8, 1.0, 1.0);
                vec3 d2 = vec3(0.2, 0.4, 0.5);
                vec3 col2 = a2 + b2 * cos(6.28318 * (c2 * t * 1.1 + d2));
                
                // Accent: Purple/magenta sparkles (subtle)
                vec3 a3 = vec3(0.08, 0.02, 0.15);      // Dark purple
                vec3 b3 = vec3(0.3, 0.05, 0.4);        // Magenta accent
                vec3 c3 = vec3(1.0, 0.8, 1.2);
                vec3 d3 = vec3(0.7, 0.3, 0.8);
                vec3 col3 = a3 + b3 * cos(6.28318 * (c3 * t * 0.7 + d3));
                
                // Blend: heavily favor dark navy, with cyan edges, rare magenta
                float blend1 = 0.3 + 0.2 * sin(time * 0.08);
                float blend2 = 0.15 + 0.1 * sin(time * 0.12 + 2.0);
                return mix(mix(col1, col2, blend1), col3, blend2 * 0.15);
            }

            // Orbit trap data structure
            struct OrbitData {
                float iter;
                float minDistCircle;   // Distance to circle trap
                float minDistLine;     // Distance to line trap
                float minDistPoint;    // Distance to point trap
                float avgAngle;        // Average orbital angle
                float finalMag;        // Final magnitude
                vec2 lastZ;            // Last z value
            };

            // Main fractal iteration with orbit trap data collection
            // USES RESCALING to prevent underflow at deep zoom
            OrbitData get_iter_full(vec2 screen_coord) {
                OrbitData data;
                data.minDistCircle = 1e10;
                data.minDistLine = 1e10;
                data.minDistPoint = 1e10;
                data.avgAngle = 0.0;
                data.finalMag = 0.0;
                data.lastZ = vec2(0.0);
                
                vec2 rel_uv = (screen_coord * 2.0 - u_resolution.xy) / u_resolution.y;
                // Use u_invZoom (computed in JS with float64) instead of 1.0/u_zoom.x for deep zoom precision
                vec2 dx = ds_mul(vec2(rel_uv.x, 0.0), u_invZoom);
                vec2 dy = ds_mul(vec2(rel_uv.y, 0.0), u_invZoom);
                
                // RESCALING: Track scale factor S such that w = z/S, d = c/S
                // When |w| gets too small, we rescale to keep it near 1
                float scaleFactor = 1.0;  // S in the theory - starts at 1
                float logScale = 0.0;     // log2(scaleFactor) tracked for precision
                
                // Rescale thresholds
                const float RESCALE_THRESHOLD_LOW = 1e-6;   // Rescale up when below this
                const float RESCALE_THRESHOLD_HIGH = 1e6;   // Rescale down when above this
                const float RESCALE_FACTOR = 1e4;           // Factor to rescale by
                
                float max_iter = u_maxIter;
                
                // ====== STABLE ANIMATED POWER ======
                float rawOsc = sin(u_time * 0.08) * 0.5 + sin(u_time * 0.13) * 0.3;
                float easedOsc = sign(rawOsc) * pow(abs(rawOsc), 1.5);
                float animatedPower = 1.2 + easedOsc * 0.15;
                float perturbStrength = (animatedPower - 2.0) * 0.3;
                
                // Orbit trap parameters
                float trapCircleRadius = 0.5 + 0.3 * sin(u_time * 0.2);
                vec2 trapPoint = vec2(0.3 * cos(u_time * 0.15), 0.3 * sin(u_time * 0.18));
                float trapLineAngle = u_time * 0.1;
                vec2 trapLineDir = vec2(cos(trapLineAngle), sin(trapLineAngle));
                
                float angleSum = 0.0;
                
                for (float i = 0.0; i < 4000.0; i++) {
                    if (i >= max_iter) break;
                    
                    // ====== RESCALING CHECK ======
                    // Check if dx/dy magnitude is getting too small (underflow risk)
                    float deltaMag = sqrt(dx.x * dx.x + dy.x * dy.x);
                    if (deltaMag > 0.0 && deltaMag < RESCALE_THRESHOLD_LOW) {
                        // Rescale UP: multiply dx, dy by RESCALE_FACTOR to prevent underflow
                        dx.x *= RESCALE_FACTOR;
                        dx.y *= RESCALE_FACTOR;
                        dy.x *= RESCALE_FACTOR;
                        dy.y *= RESCALE_FACTOR;
                        scaleFactor /= RESCALE_FACTOR;  // Track inverse scale
                        logScale -= log2(RESCALE_FACTOR);
                    } else if (deltaMag > RESCALE_THRESHOLD_HIGH) {
                        // Rescale DOWN: divide dx, dy by RESCALE_FACTOR to prevent overflow
                        dx.x /= RESCALE_FACTOR;
                        dx.y /= RESCALE_FACTOR;
                        dy.x /= RESCALE_FACTOR;
                        dy.y /= RESCALE_FACTOR;
                        scaleFactor *= RESCALE_FACTOR;
                        logScale += log2(RESCALE_FACTOR);
                    }
                    
                    // Standard high-precision z² iteration
                    // Note: The DS arithmetic now operates on rescaled values
                    vec2 fixX_dx = ds_mul(u_fixX_h, dx);
                    vec2 fixY_dy = ds_mul(u_fixY_h, dy);
                    vec2 fixX_dy = ds_mul(u_fixX_h, dy);
                    vec2 fixY_dx = ds_mul(u_fixY_h, dx);
                    vec2 dx2 = ds_mul(dx, dx);
                    vec2 dy2 = ds_mul(dy, dy);
                    vec2 dxdy = ds_mul(dx, dy);
                    vec2 term1_x = ds_sub(fixX_dx, fixY_dy);
                    term1_x = ds_add(term1_x, term1_x);
                    
                    // When S != 1, the dx² terms are scaled by S²
                    // We need to divide by S to compensate: dx = (2*fixX*dx + dx²) but dx²/S
                    if (abs(scaleFactor - 1.0) > 0.001) {
                        dx2.x *= scaleFactor;
                        dx2.y *= scaleFactor;
                        dy2.x *= scaleFactor;
                        dy2.y *= scaleFactor;
                        dxdy.x *= scaleFactor;
                        dxdy.y *= scaleFactor;
                    }
                    
                    dx = ds_add(term1_x, ds_sub(dx2, dy2));
                    vec2 term1_y = ds_add(fixX_dy, fixY_dx);
                    term1_y = ds_add(term1_y, term1_y);
                    dy = ds_add(term1_y, ds_add(dxdy, dxdy));
                    
                    // Get current z using FULL Double-Single precision
                    // Apply inverse scale to get true z values for escape check
                    vec2 z_ds_x = ds_add(ds_mul(dx, vec2(scaleFactor, 0.0)), u_fixX_h);
                    vec2 z_ds_y = ds_add(ds_mul(dy, vec2(scaleFactor, 0.0)), u_fixY_h);
                    
                    // High-precision magnitude squared: mag2 = zx^2 + zy^2
                    vec2 mag2 = ds_add(ds_mul(z_ds_x, z_ds_x), ds_mul(z_ds_y, z_ds_y));
                    float mag = sqrt(max(0.0, mag2.x));
                    
                    // ====== PERTURBATION: Add small power correction ======
                    if (mag > 0.001 && mag < 100.0 && abs(perturbStrength) > 0.001) {
                        float theta = atan(z_ds_y.x, z_ds_x.x);
                        float extraPow = animatedPower - 2.0;
                        float r_extra = pow(mag, extraPow);
                        float theta_extra = extraPow * theta;
                        
                        float perturb_x = mag * mag * (r_extra * cos(theta_extra) - 1.0);
                        float perturb_y = mag * mag * (r_extra * sin(theta_extra));
                        
                        // Apply perturbation in scaled space
                        dx.x += perturb_x * perturbStrength / scaleFactor;
                        dy.x += perturb_y * perturbStrength / scaleFactor;
                        
                        // Recalculate z after perturbation
                        z_ds_x = ds_add(ds_mul(dx, vec2(scaleFactor, 0.0)), u_fixX_h);
                        z_ds_y = ds_add(ds_mul(dy, vec2(scaleFactor, 0.0)), u_fixY_h);
                        mag2 = ds_add(ds_mul(z_ds_x, z_ds_x), ds_mul(z_ds_y, z_ds_y));
                        mag = sqrt(max(0.0, mag2.x));
                    }
                    
                    vec2 z = vec2(z_ds_x.x, z_ds_y.x);
                    
                    // Collect orbit trap distances
                    float distCircle = abs(mag - trapCircleRadius);
                    data.minDistCircle = min(data.minDistCircle, distCircle);
                    
                    float distPoint = length(z - trapPoint);
                    data.minDistPoint = min(data.minDistPoint, distPoint);
                    
                    float distLine = abs(dot(z, vec2(-trapLineDir.y, trapLineDir.x)));
                    data.minDistLine = min(data.minDistLine, distLine);
                    
                    angleSum += atan(z_ds_y.x, z_ds_x.x);
                    
                    // Escape check using high-precision magnitude squared
                    float escapeR = 1.0 + 2.0 * animatedPower;
                    if (mag2.x > escapeR * escapeR) {
                        float r2 = mag2.x;
                        float nu = log2(log2(r2 + 1.0) / log2(escapeR));
                        data.iter = i + 1.0 - nu;
                        data.avgAngle = angleSum / (i + 1.0);
                        data.finalMag = mag;
                        data.lastZ = z;
                        return data;
                    }
                    data.lastZ = z;
                }
                data.iter = max_iter;
                data.avgAngle = angleSum / max_iter;
                data.finalMag = length(data.lastZ);
                return data;
            }

            // Dark void effect (inverted glow - creates dark arms)
            vec3 addGlow(vec3 col, float iter, float maxIter, OrbitData data) {
                // Edge darkness - stronger near escape boundary
                float edgeness = 1.0 - (iter / maxIter);
                float glow = exp(-iter * 0.015) * 2.5;
                
                // Orbit trap darkness contributions
                float circleGlow = exp(-data.minDistCircle * 8.0) * 0.6;
                float pointGlow = exp(-data.minDistPoint * 12.0) * 0.8;
                float lineGlow = exp(-data.minDistLine * 6.0) * 0.4;
                
                // Darken where there would be bright bands (inverted)
                float totalDarkness = glow * 0.3 + circleGlow * 0.5 + pointGlow * 0.4 + lineGlow * 0.6;
                
                // Multiply to darken - Waterfall palette void colors
                vec3 darkFactor = vec3(1.0) - vec3(0.05, 0.1, 0.15) * glow;        // Navy tinted darkness
                darkFactor -= vec3(0.1, 0.25, 0.3) * circleGlow;    // Dark cyan void
                darkFactor -= vec3(0.1, 0.2, 0.25) * pointGlow;     // Dark teal void
                darkFactor -= vec3(0.15, 0.1, 0.25) * lineGlow;     // Dark indigo void
                
                // Clamp to prevent negative colors
                darkFactor = max(darkFactor, vec3(0.03, 0.03, 0.08));
                
                return col * darkFactor;
            }

            // Second fractal layer (Burning Ship variation)
            float burningShipLayer(vec2 screen_coord) {
                vec2 rel_uv = (screen_coord * 2.0 - u_resolution.xy) / u_resolution.y;
                vec2 c = rel_uv / u_zoom.x * 0.5 + vec2(-0.5, -0.5);
                vec2 z = vec2(0.0);
                
                for (float i = 0.0; i < 100.0; i++) {
                    z = vec2(abs(z.x), abs(z.y)); // Burning ship fold
                    float x = z.x * z.x - z.y * z.y + c.x;
                    float y = 2.0 * z.x * z.y + c.y;
                    z = vec2(x, y);
                    if (dot(z, z) > 256.0) {
                        return i / 100.0;
                    }
                }
                return 1.0;
            }

            // Third layer - Mandelbrot with different parameters
            float mandelbrotLayer(vec2 screen_coord) {
                vec2 rel_uv = (screen_coord * 2.0 - u_resolution.xy) / u_resolution.y;
                vec2 c = rel_uv / u_zoom.x * 0.3 + vec2(
                    -0.7 + 0.1 * sin(u_time * 0.08),
                    0.0 + 0.1 * cos(u_time * 0.11)
                );
                vec2 z = vec2(0.0);
                
                for (float i = 0.0; i < 80.0; i++) {
                    float x = z.x * z.x - z.y * z.y + c.x;
                    float y = 2.0 * z.x * z.y + c.y;
                    z = vec2(x, y);
                    if (dot(z, z) > 256.0) {
                        return i / 80.0;
                    }
                }
                return 1.0;
            }

            void main() {
                // 2x2 supersampling for anti-aliasing
                vec3 totalCol = vec3(0.0);
                float aa = 2.0;
                
                for (float ax = 0.0; ax < aa; ax++) {
                    for (float ay = 0.0; ay < aa; ay++) {
                        vec2 offset = (vec2(ax, ay) - 0.5 * (aa - 1.0)) / aa;
                        vec2 sampleCoord = gl_FragCoord.xy + offset;
                        
                        // ===== MULTI-RIPPLE DISTORTION =====
                        // Each ripple expands as a shockwave from center based on its birth time
                        vec2 center = u_resolution.xy * 0.5;
                        vec2 toPixel = sampleCoord - center;
                        float dist = length(toPixel);
                        float distNorm = dist / u_resolution.y;
                        vec2 rippleDir = length(toPixel) > 0.001 ? normalize(toPixel) : vec2(0.0);
                        
                        float totalWaveDisplacement = 0.0;
                        
                        for (int i = 0; i < 4; i++) {
                            float timeSinceBirth = u_ripples[i].x;
                            float intensity = u_ripples[i].y;
                            
                            if (intensity > 0.001) {
                                // Ripple expands outward from center over time
                                // Wave front position = timeSinceBirth * expansionSpeed
                                float expansionSpeed = 1.5;  // How fast the wavefront moves
                                float waveRadius = timeSinceBirth * expansionSpeed;
                                
                                // Distance from this pixel to the wavefront
                                float distFromWave = distNorm - waveRadius;
                                
                                // Gaussian envelope around the wavefront
                                float waveWidth = 0.15;  // Width of the wave band
                                float envelope = exp(-distFromWave * distFromWave / (waveWidth * waveWidth));
                                
                                // Oscillation within the wave
                                float freq = 25.0;  // Wave frequency
                                float wave = sin(distNorm * freq - timeSinceBirth * 18.0);
                                
                                // Combine: wave only visible near the expanding wavefront
                                totalWaveDisplacement += wave * envelope * intensity;
                            }
                        }
                        
                        // Apply combined ripple distortion
                        sampleCoord += rippleDir * totalWaveDisplacement * u_resolution.y * 0.15;
                        
                        // Get main fractal data with orbit traps
                        OrbitData data = get_iter_full(sampleCoord);
                        float iter = data.iter;
                        
                        float max_iter_comp = u_maxIter;
                        
                        vec3 col = vec3(0.0);
                        
                        if (iter < max_iter_comp - 0.5) {
                            // Base color from iteration count with enhanced palette
                            col = palette(iter * 0.018 + u_time * 0.006, u_time);
                            
                            // Orbit trap coloring contributions
                            float trapMix = 0.0;
                            
                            // Circle trap - bright cyan (waterfall glow)
                            float circleInfluence = exp(-data.minDistCircle * 5.0);
                            col = mix(col, vec3(0.0, 0.8, 1.0), circleInfluence * 0.4);
                            
                            // Point trap - teal/aqua
                            float pointInfluence = exp(-data.minDistPoint * 8.0);
                            col = mix(col, vec3(0.2, 0.7, 0.8), pointInfluence * 0.5);
                            
                            // Line trap - magenta sparkle
                            float lineInfluence = exp(-data.minDistLine * 4.0);
                            col = mix(col, vec3(0.8, 0.2, 1.0), lineInfluence * 0.3);
                            
                            // Angular coloring for spiral effect
                            float angleFactor = 0.5 + 0.5 * sin(data.avgAngle * 3.0 + u_time * 0.5);
                            col *= 0.8 + 0.2 * angleFactor;
                            
                            // Add glow effects
                            col = addGlow(col, iter, max_iter_comp, data);
                            
                            // Multi-layer fractal blending
                            float burnLayer = burningShipLayer(sampleCoord);
                            float mandLayer = mandelbrotLayer(sampleCoord);
                            
                            // Subtle overlay of secondary fractals
                            vec3 burnColor = palette(burnLayer * 1.5 + 0.3, u_time) * 0.15;
                            vec3 mandColor = palette(mandLayer * 2.0 + 0.5, u_time) * 0.1;
                            
                            col += burnColor * (0.3 + 0.2 * sin(u_time * 0.4));
                            col += mandColor * (0.2 + 0.1 * cos(u_time * 0.35));
                            
                        } else {
                            // ====== UNDERTALE WATERFALL INTERIOR ======
                            vec2 uv = sampleCoord / u_resolution.xy;
                            
                            // Use the final orbit position for dynamic patterns
                            vec2 lastZ = data.lastZ;
                            float lastMag = length(lastZ);
                            float lastAngle = atan(lastZ.y, lastZ.x);
                            
                            // Animated ripple patterns based on orbit (slowed down)
                            float ripple1 = sin(lastMag * 15.0 + u_time * 0.8) * 0.5 + 0.5;
                            float ripple2 = sin(lastAngle * 8.0 - u_time * 0.6) * 0.5 + 0.5;
                            float ripple3 = sin((lastZ.x + lastZ.y) * 12.0 + u_time * 1.0) * 0.5 + 0.5;
                            
                            // Interference pattern
                            float interference = sin(lastZ.x * 25.0) * sin(lastZ.y * 25.0);
                            interference += sin((lastZ.x - lastZ.y) * 18.0 + u_time * 0.4);
                            interference *= 0.5;
                            
                            // Waterfall base - very deep navy (near black)
                            vec3 nebulaBase = vec3(
                                0.01 + 0.01 * sin(lastAngle * 3.0 + u_time * 0.15),
                                0.02 + 0.02 * sin(lastMag * 5.0 + u_time * 0.2),
                                0.06 + 0.04 * sin(lastAngle * 2.0 - u_time * 0.1)
                            );
                            
                            // Waterfall ripple colors - subtle cyan and blue tones
                            col = nebulaBase;
                            col += vec3(0.0, 0.04, 0.1) * ripple1;    // Deep blue ripple
                            col += vec3(0.0, 0.08, 0.12) * ripple2;   // Cyan ripple
                            col += vec3(0.01, 0.05, 0.08) * ripple3;  // Teal ripple
                            col += vec3(0.0, 0.03, 0.06) * interference;
                            
                            // Bioluminescent glow - Waterfall style
                            float circleGlow = exp(-data.minDistCircle * 2.0);
                            float pointGlow = exp(-data.minDistPoint * 3.0);
                            float lineGlow = exp(-data.minDistLine * 1.5);
                            
                            col += vec3(0.0, 0.4, 0.6) * circleGlow * 0.8;    // Cyan circle glow
                            col += vec3(0.0, 0.6, 0.5) * pointGlow * 0.7;     // Teal point glow
                            col += vec3(0.1, 0.3, 0.8) * lineGlow * 0.6;      // Blue line glow
                            
                            // Spiral arms - blue tones
                            float spiral = sin(data.avgAngle * 5.0 + lastMag * 10.0 + u_time * 0.7);
                            col += vec3(0.0, 0.12, 0.22) * (spiral * 0.5 + 0.5) * 0.4;
                            
                            // Slow, gentle breathing effect
                            float pulse = 0.85 + 0.15 * sin(u_time * 0.5 + lastMag * 3.0);
                            col *= pulse;
                            
                            // Nebula texture with waterfall feel - INCREASED BRIGHTNESS
                            float nebulaNoiseVal = fbm(lastZ * 3.0 + u_time * 0.03);
                            col *= 1.2 + 0.6 * nebulaNoiseVal;
                            
                            // Edge glow - bright cyan near boundary
                            float edgeDist = 1.0 - smoothstep(0.0, 2.0, lastMag);
                            col += vec3(0.0, 0.2, 0.3) * edgeDist * 0.6;
                        }
                        
                        // Noise overlay for texture
                        vec2 noiseCoord = sampleCoord * 0.003 + vec2(u_time * 0.02, u_time * 0.015);
                        float n = fbm(noiseCoord);
                        col *= 0.92 + 0.08 * n;  // Subtle texture
                        
                        // Additional fine grain noise
                        float grain = hash(sampleCoord + u_time * 100.0);
                        col += (grain - 0.5) * 0.015;
                        
                        // Vignette effect
                        vec2 vignetteUV = sampleCoord / u_resolution.xy - 0.5;
                        float vignette = 1.0 - dot(vignetteUV, vignetteUV) * 0.5;
                        col *= vignette;
                        
                        totalCol += col;
                    }
                }
                
                totalCol /= (aa * aa);
                
                // Final tone mapping and color grading
                totalCol = pow(totalCol, vec3(0.95));  // Slight gamma
                totalCol = mix(totalCol, totalCol * vec3(1.1, 1.0, 1.15), 0.2);  // Color grade
                
                fragColor = vec4(clamp(totalCol, 0.0, 1.0), 1.0);
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
            fetch('/file=fractal_config.json').then(r => r.json()).then(c => { cfg = {...cfg, ...c}; console.log('Fractal config loaded:', cfg); }).catch(() => console.log('Using default fractal config'));

            const startTime = Date.now();
            let currentZoomLog = 0;  // Start zoomed out
            let actualZoomRate = cfg.zoom.rate;
            let zoomDirection = 1;  // +1 = zoom in, -1 = zoom out
            
            // MOMENTUM-BASED CAMERA SYSTEM
            let centerX = 0;
            let centerY = 0;
            let centerVelX = 0;  // Velocity for momentum
            let centerVelY = 0;
            let targetCenterY = 0;
            let centerInitialized = false;
            let stdDevHistory = [400, 400, 400]; // Rolling history of last 3 stdDevs
            
            // SMOOTH TRANSITIONS
            let smoothPauseFactor = 1.0;     // 1.0 = normal speed, 0.5 = paused
            let smoothZoomRate = cfg.zoom.rate;  // Smoothed zoom rate
            let isZoomPaused = false;
            
            // Camera momentum parameters
            const cameraMomentum = 0.995;    // How much velocity is retained each frame (higher = more momentum)
            const cameraAccel = 0.0003;      // How fast camera accelerates toward target
            const maxCameraSpeed = 0.001;    // Maximum camera velocity per frame
            
            // STUCK DETECTION - escape when screen is solid color for too long
            let stuckTimer = 0;              // How long we've been in solid color
            const stuckThreshold = 0.1;      // Seconds before triggering escape (0.1 per user request)
            let stuckZoomOutTimer = 0;       // Seconds to zoom out for recovery
            let isInsideFractal = false;     // true = stuck inside (dark), false = stuck outside (escaping fast)
            let escapeVelX = 0;              // Corrective velocity to escape
            let escapeVelY = 0;
            const escapeAccel = 0.05;        // INCREASED 100x - how fast to accelerate when escaping

            function splitDouble(d) {
                const hi = Math.fround(d);
                const lo = d - hi;
                return [hi, lo];
            }

            let lastFrameTime = performance.now();
            let smoothedDelta = 0.0166; // Initial guess for 60fps
            let accumulatedTime = 0;
            let accumulatedZoomLog = 0;

            // Ripple State - MULTI-RIPPLE SYSTEM
            // Each beat spawns a new ripple wave with its own birth time
            const MAX_RIPPLES = 6;  // Number of concurrent ripple waves
            let ripples = [];  // Array of {birthTime, intensity, type} objects
            let lastBeatEnergy = 0;
            let avgBeatDelta = 0.01; // Adaptive threshold baseline
            let globalAudioTime = 0;  // Cumulative audio-synced time
            
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
                        // Reset stats here too just in case
                        avgBeatDelta = 0.01;
                     };
                     const onLoaded = () => {
                        avgBeatDelta = 0.01;
                        lastBeatEnergy = 0;
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
                         ripples.push({
                             birthTime: globalAudioTime,
                             intensity: intensity,
                             type: rippleType
                         });
                         
                         // Keep pool size limited - remove oldest when full
                         while (ripples.length > MAX_RIPPLES) {
                             ripples.shift();
                         }
                    }
                    lastBeatEnergy = beatEnergy;
                    
                    // Advance global audio time
                    globalAudioTime += smoothedDelta;
                    
                    // NaN SAFETY GUARD
                    if (isNaN(globalAudioTime)) globalAudioTime = 0;
                    if (isNaN(avgBeatDelta)) avgBeatDelta = 0.01;
                    
                    // Update ripple intensities with decay and remove dead ripples
                    ripples = ripples.filter(r => {
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
                
                accumulatedTime += smoothedDelta * audioMorphBoost;
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

                // Morphing Julia set - Use accumulatedTime for phi
                // SLOW DOWN MORPH AS ZOOM DEEPENS - prevents chaos at deep zoom
                // Use smooth pause factor for gradual transitions (not abrupt)
                const zoomMorphSlowdown = 1.0 + accumulatedZoomLog / 5.0;  // At zoomLog=10, morph is 3x slower
                const morphRate = cfg.animation.morphRate / zoomMorphSlowdown * smoothPauseFactor;
                const phi = accumulatedTime * morphRate;
                const spiralRadius = 0.35 - 0.08 * Math.sin(phi * 0.7);
                const cx = spiralRadius * Math.cos(phi) - 0.1 * Math.cos(2.0 * phi + 0.3);
                const cy = spiralRadius * Math.sin(phi) - 0.1 * Math.sin(2.0 * phi + 0.3);
                const wx = 1.0 - 4.0 * cx;
                const wy = -4.0 * cy;
                const r_w = Math.sqrt(wx * wx + wy * wy);
                let sx = Math.sqrt((r_w + wx) * 0.5);
                let sy = Math.sqrt((r_w - wx) * 0.5);
                if (wy < 0.0) sy = -sy;
                
                // Calculate attractive fixed point (for initialization/reset)
                const fixX = (1.0 - sx) * 0.5;
                const fixY = -sy * 0.5;
                
                // Calculate zoom
                const zoom = Math.exp(accumulatedZoomLog);
                
                // CPU-SIDE ITERATION PROBE - test if a point escapes (JULIA SET)
                // In Julia set: z₀ = probe point, c = morphing parameter (cx, cy)
                function probeEscapes(px, py, maxIter) {
                    let zx = px, zy = py;  // Start at probe point (Julia set)
                    for (let i = 0; i < maxIter; i++) {
                        const zx2 = zx * zx, zy2 = zy * zy;
                        if (zx2 + zy2 > 4) return i;  // Escaped - return iteration count
                        const newZx = zx2 - zy2 + cx;  // Use Julia set c parameter
                        const newZy = 2 * zx * zy + cy;
                        zx = newZx; zy = newZy;
                    }
                    return maxIter;  // Didn't escape - in set
                }
                
                // CENTER ON JULIA SET BOUNDARY
                // Find a point on the boundary by probing outward from origin
                // in the direction of c (where structure is most interesting)
                const cMag = Math.sqrt(cx * cx + cy * cy);
                let dirX = cMag > 0.001 ? cx / cMag : 1.0;
                let dirY = cMag > 0.001 ? cy / cMag : 0.0;
                
                // Binary search for boundary: find where iteration count changes
                let lo = 0.0, hi = 2.0;  // Search range along the direction
                const boundaryIter = 100;  // Quick boundary test iterations
                
                for (let bisect = 0; bisect < 12; bisect++) {
                    const mid = (lo + hi) * 0.5;
                    const px = mid * dirX;
                    const py = mid * dirY;
                    const iter = probeEscapes(px, py, boundaryIter);
                    if (iter < boundaryIter) {
                        hi = mid;  // Escaped - move inward
                    } else {
                        lo = mid;  // Didn't escape - move outward
                    }
                }
                
                // Target center is slightly inside the boundary
                const boundaryDist = (lo + hi) * 0.5;
                targetCenterX = boundaryDist * dirX * 0.95;
                targetCenterY = boundaryDist * dirY * 0.95;
                
                // ===== BOUNDARY QUALITY DETECTION =====
                // Probe multiple points around the center to detect if there's actual fractal detail
                // If all points have similar escape times, we're in deadspace -> pause zoom
                const probeScale = 0.5 / zoom;  // Scale probes to current view
                const probePoints = [
                    [targetCenterX + probeScale, targetCenterY],
                    [targetCenterX - probeScale, targetCenterY],
                    [targetCenterX, targetCenterY + probeScale],
                    [targetCenterX, targetCenterY - probeScale],
                    [targetCenterX + probeScale * 0.7, targetCenterY + probeScale * 0.7],
                    [targetCenterX - probeScale * 0.7, targetCenterY - probeScale * 0.7],
                ];
                
                // Get iteration counts for each probe
                // IMPROVEMENT: Use higher iteration count for quality check to see deeper structure
                const qualityIter = 1000;
                const probeIters = probePoints.map(p => probeEscapes(p[0], p[1], qualityIter));
                
                // Calculate variance in iteration counts - high variance = good boundary detail
                const meanIter = probeIters.reduce((a, b) => a + b, 0) / probeIters.length;
                const variance = probeIters.reduce((sum, i) => sum + (i - meanIter) ** 2, 0) / probeIters.length;
                const stdDev = Math.sqrt(variance);
                
                // ROLLING AVERAGE (size 3) - as requested by user
                stdDevHistory.push(stdDev);
                if (stdDevHistory.length > 3) stdDevHistory.shift();
                const avgStdDev = stdDevHistory.reduce((a, b) => a + b, 0) / stdDevHistory.length;
                
                // FORCE STUCK if we are hitting iteration limits (solid black inside or solid outside)
                const isTooDeep = meanIter > qualityIter * 0.95;  // Stuck deep inside set
                const isTooShallow = meanIter < 15;               // Stuck far outside set
                
                // ADAPTIVE ZOOM PAUSE: If variance is too low, pause zoom until edges reappear
                const minVarianceThreshold = 400;  // Threshold
                
                // Good boundary requires:
                // 1. High variance (detail)
                // 2. Not stuck deep inside (max iters)
                // 3. Not stuck far outside (min iters)
                const hasGoodBoundary = (avgStdDev > minVarianceThreshold) && !isTooDeep && !isTooShallow;
                isZoomPaused = !hasGoodBoundary;
                
                // DEBUG: Log every 60 frames (~1 sec) to trace stuck detection
                if (Math.floor(accumulatedTime * 60) % 60 === 0) {
                    console.log(`Boundary check: avgStdDev=${avgStdDev.toFixed(2)} (raw=${stdDev.toFixed(2)}), mean=${meanIter.toFixed(0)}, deep=${isTooDeep}, shallow=${isTooShallow}, stuckTimer=${stuckTimer.toFixed(1)}s`);
                }
                
                // ===== STUCK DETECTION & ESCAPE =====
                // If screen is solid color for stuckThreshold seconds, apply corrective velocity
                
                // GRACE PERIOD: No stuck recovery in first 20s
                if (accumulatedTime < 20.0) {
                    stuckTimer = 0;
                } else if (!hasGoodBoundary) {
                    stuckTimer += smoothedDelta;
                    
                    // Determine if we're stuck inside fractal (high iter = didn't escape = inside)
                    // or outside fractal (low iter = escaped quickly = outside)
                    isInsideFractal = meanIter > boundaryIter * 0.8;  // Most points didn't escape
                    
                    if (stuckTimer > stuckThreshold) {
                        // TRIGGER 20s ZOOM-OUT RECOVERY
                        stuckZoomOutTimer = 20.0;
                        stuckTimer = 0;
                        console.log("STUCK! Triggering 20s Zoom-Out Recovery");
                        
                        // Create escape velocity based on position relative to origin
                        const distFromOrigin = Math.sqrt(centerX * centerX + centerY * centerY);
                        // DON'T scale by zoom - we want strong escape regardless of zoom level
                        
                        if (distFromOrigin > 0.001) {
                            // Normalize direction from origin
                            const normX = centerX / distFromOrigin;
                            const normY = centerY / distFromOrigin;
                            
                            if (isInsideFractal) {
                                // Stuck INSIDE - move AWAY from origin (outward toward boundary)
                                escapeVelX += normX * escapeAccel;
                                escapeVelY += normY * escapeAccel;
                                console.log(`STUCK INSIDE for ${stuckTimer.toFixed(1)}s - escaping OUTWARD`);
                            } else {
                                // Stuck OUTSIDE - move TOWARD origin (inward toward boundary)
                                escapeVelX -= normX * escapeAccel;
                                escapeVelY -= normY * escapeAccel;
                                console.log(`STUCK OUTSIDE for ${stuckTimer.toFixed(1)}s - escaping INWARD`);
                            }
                        } else {
                            // At origin - move in direction of c parameter
                            escapeVelX += (cx > 0 ? 1 : -1) * escapeAccel;
                            escapeVelY += (cy > 0 ? 1 : -1) * escapeAccel;
                            console.log(`STUCK at ORIGIN for ${stuckTimer.toFixed(1)}s - escaping toward c`);
                        }
                    }
                } else {
                    // Complexity returned - reset stuck timer and decay escape velocity
                    stuckTimer = 0;
                    escapeVelX *= 0.9;  // Decay escape velocity
                    escapeVelY *= 0.9;
                }
                
                // SMOOTH PAUSE FACTOR - gradually transition between paused/unpaused
                const targetPauseFactor = isZoomPaused ? 0.5 : 1.0;
                smoothPauseFactor = smoothPauseFactor * 0.98 + targetPauseFactor * 0.02;  // Smooth 50-frame transition
                
                // SMOOTH ZOOM RATE - interpolate toward target rate
                const targetZoomRate = hasGoodBoundary ? cfg.zoom.rate : 0;
                smoothZoomRate = smoothZoomRate * 0.95 + targetZoomRate * 0.05;  // 20-frame transition
                
                // Apply Audio Boost (bass thump)
                let finalZoomRate = smoothZoomRate;
                if (isAudioActive && audioZoomBoost > 0) {
                     finalZoomRate += audioZoomBoost;
                }
                
                // Dynamic zoom speed limit based on current zoom level
                // Deeper zooms should have slower max zoom rate to maintain precision
                const dynamicMaxRate = cfg.zoom.rate / (1 + accumulatedZoomLog * 0.1);
                let clampedZoomRate = Math.min(finalZoomRate, dynamicMaxRate);
                
                // FORCE COMPLETE STOP when stuck - don't zoom at all until complexity returns
                if (stuckTimer > stuckThreshold) {
                    clampedZoomRate = 0;  // Hard stop
                }
                
                // ZOOM-OUT RECOVERY OVERRIDE
                let effectiveZoomDirection = zoomDirection;
                if (stuckZoomOutTimer > 0) {
                    stuckZoomOutTimer -= smoothedDelta;
                    effectiveZoomDirection = -1; // Force zoom out
                    clampedZoomRate = cfg.zoom.rate * 4.0; // EVEN FASTER zoom out (4x instead of 2x)
                    
                    // IMPORTANT: When zooming out for recovery, we DON'T care if boundary is "good" or not
                    // we just want to get out. So this override is final.
                    if (stuckZoomOutTimer <= 0) {
                        console.log("Zoom-Out Recovery complete. Resuming normal zoom.");
                    }
                }
                
                // Accumulate zoom with smooth rate
                accumulatedZoomLog += clampedZoomRate * smoothedDelta * effectiveZoomDirection;
                
                // Re-check zoom bounds after accumulation
                if (accumulatedZoomLog >= cfg.zoom.maxLog) {
                    accumulatedZoomLog = cfg.zoom.maxLog;
                    zoomDirection = -1;
                } else if (accumulatedZoomLog <= cfg.zoom.minLog) {
                    accumulatedZoomLog = cfg.zoom.minLog;
                    zoomDirection = 1;
                }
                
                // ===== MOMENTUM-BASED CAMERA =====
                // Physics: accelerate toward target, retain momentum
                // This gives ultra-smooth movement that doesn't lose precision at deep zoom
                if (!centerInitialized) {
                    centerX = targetCenterX;
                    centerY = targetCenterY;
                    centerVelX = 0;
                    centerVelY = 0;
                    centerInitialized = true;
                } else {
                    // Calculate acceleration toward target
                    const dx = targetCenterX - centerX;
                    const dy = targetCenterY - centerY;
                    
                    // Scale acceleration by zoom (smaller movements at deep zoom)
                    const zoomScale = 1.0 / zoom;
                    const accelX = dx * cameraAccel;
                    const accelY = dy * cameraAccel;
                    
                    // Apply momentum (retain previous velocity) and acceleration
                    centerVelX = centerVelX * cameraMomentum + accelX + escapeVelX;
                    centerVelY = centerVelY * cameraMomentum + accelY + escapeVelY;
                    
                    // Clamp velocity to prevent overshooting (scale by zoom)
                    const maxSpeed = maxCameraSpeed * zoomScale;
                    const speed = Math.sqrt(centerVelX * centerVelX + centerVelY * centerVelY);
                    if (speed > maxSpeed) {
                        centerVelX *= maxSpeed / speed;
                        centerVelY *= maxSpeed / speed;
                    }
                    
                    // Apply velocity to position
                    centerX += centerVelX;
                    centerY += centerVelY;
                }

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
                const sortedRipples = [...ripples].sort((a, b) => b.intensity - a.intensity).slice(0, 4);
                for (let i = 0; i < 4; i++) {
                    if (i < sortedRipples.length) {
                        const r = sortedRipples[i];
                        const timeSinceBirth = globalAudioTime - r.birthTime;
                        gl.uniform4f(locRipples[i], timeSinceBirth, r.intensity, 0.0, 0.0);
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

