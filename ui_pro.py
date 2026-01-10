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
    body, .gradio-container {
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
    .block, .form, .panel, .container, .wrap, .gradio-container {
        background: rgba(10, 25, 50, 0.3) !important;
        border: 1px solid rgba(0, 255, 0, 0.2) !important;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.8) !important;
        border-radius: 12px !important;
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
    .gr-audio, [data-testid="waveform-slot"], .waveform-container, audio {
        display: none !important;
    }
    """
    
    with gr.Blocks(title="Pro AI Agent") as demo:
        gr.Markdown("""
        # 🚀 Pro AI Agent
        **Neural Interface** | Live Thought Stream | Visual Feed
        """)
        
        with gr.Row():
            # LEFT COLUMN: Chat + Thoughts
            with gr.Column(scale=1):
                gr.Markdown("### 💬 Chat")
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
                        label="🧠 Planning Mode",
                        value=False,
                        info="Think before acting"
                    )
                    continue_btn = gr.Button("▶️ Continue", variant="secondary")
                    clear_btn = gr.Button("🗑️ Clear All")
                
                model_dropdown = gr.Dropdown(
                    choices=models,
                    value=DEFAULT_MODEL if DEFAULT_MODEL in models else (models[0] if models else "qwen2.5:14b"),
                    label="Model",
                    interactive=True
                )
                
                gr.Markdown("### 🧠 Thought Stream")
                thought_display = gr.Textbox(
                    label="",
                    value="Waiting for input...",
                    lines=12,
                    max_lines=15,
                    interactive=False
                )
            
            # RIGHT COLUMN: Live Visual Feed
            with gr.Column(scale=1):
                gr.Markdown("### 👁️ Live Visual Feed")
                visual_feed = gr.Image(
                    label="What the AI sees/controls",
                    type="filepath",
                    height=500
                )
                
                with gr.Row():
                    refresh_btn = gr.Button("📷 Capture Screen")
                
                gr.Markdown("""
                ### Available Tools
                - 🌐 Browser: Navigate, click, type
                - 📁 Files: Read, write, search
                - 📝 Grading: Parse rubrics
                - 🎮 Game: Keys, mouse, windows
                - 📷 Screenshot: Capture screen
                """)
                
                gr.Markdown("### 🎵 Music")
                audio_player = gr.Audio(
                    label="Music Player",
                    type="filepath",
                    autoplay=True
                )
                next_btn = gr.Button("⏭️ Next Track")
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

        const fragmentShaderSource = `#version 300 es
            precision highp float;
            uniform vec2 u_resolution;
            uniform float u_time;
            uniform vec2 u_fixX_h;
            uniform vec2 u_fixY_h;
            uniform vec2 u_zoom;
            out vec4 fragColor;

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
            vec3 palette(float t) {
                vec3 a = vec3(0.015, 0.0, 0.05);   
                vec3 b = vec3(0.1, 0.7, 0.95);   
                vec3 c = vec3(1.0, 1.0, 1.0);
                vec3 d = vec3(0.65, 0.35, 0.45); 
                return a + b * cos(6.28318 * (c * t + d));
            }
            float get_iter(vec2 screen_coord) {
                vec2 rel_uv = (screen_coord * 2.0 - u_resolution.xy) / u_resolution.y;
                vec2 dx = ds_mul(vec2(rel_uv.x, 0.0), vec2(1.0 / u_zoom.x, 0.0));
                vec2 dy = ds_mul(vec2(rel_uv.y, 0.0), vec2(1.0 / u_zoom.x, 0.0));
                float max_iter = 180.0 + 45.0 * log(u_zoom.x + 1.0);
                if (max_iter > 750.0) max_iter = 750.0;
                for (float i = 0.0; i < 750.0; i++) {
                    if (i >= max_iter) break;
                    vec2 fixX_dx = ds_mul(u_fixX_h, dx);
                    vec2 fixY_dy = ds_mul(u_fixY_h, dy);
                    vec2 fixX_dy = ds_mul(u_fixX_h, dy);
                    vec2 fixY_dx = ds_mul(u_fixY_h, dx);
                    vec2 dx2 = ds_mul(dx, dx);
                    vec2 dy2 = ds_mul(dy, dy);
                    vec2 dxdy = ds_mul(dx, dy);
                    vec2 term1_x = ds_sub(fixX_dx, fixY_dy);
                    term1_x = ds_add(term1_x, term1_x);
                    dx = ds_add(term1_x, ds_sub(dx2, dy2));
                    vec2 term1_y = ds_add(fixX_dy, fixY_dx);
                    term1_y = ds_add(term1_y, term1_y);
                    dy = ds_add(term1_y, ds_add(dxdy, dxdy));
                    float cur_x = dx.x + u_fixX_h.x;
                    float cur_y = dy.x + u_fixY_h.x;
                    if (cur_x*cur_x + cur_y*cur_y > 1024.0) {
                        float r2 = cur_x*cur_x + cur_y*cur_y;
                        float nu = log2(log2(r2 + 0.00001) / 2.0);
                        return i + 1.0 - nu;
                    }
                }
                return max_iter;
            }
            void main() {
                float iter = get_iter(gl_FragCoord.xy);
                vec3 col = vec3(0.0);
                float max_iter = 180.0 + 45.0 * log(u_zoom.x + 1.0);
                if (max_iter > 750.0) max_iter = 750.0;
                if (iter < max_iter) {
                    col = palette(iter * 0.02 + u_time * 0.008);
                    col += vec3(0.15, 0.0, 0.35) * (2.0 / (iter * 0.04 + 0.1));
                } else {
                    col = vec3(0.015, 0.0, 0.05);
                }
                fragColor = vec4(col, 1.0);
            }
        `;

        function start() {
            if (document.getElementById('fractal-canvas')) return;
            const canvas = document.createElement('canvas');
            canvas.id = 'fractal-canvas';
            Object.assign(canvas.style, { position: 'fixed', top: '0', left: '0', width: '100vw', height: '100vh', zIndex: '-1', pointerEvents: 'none' });
            document.body.appendChild(canvas);
            
            const gl = canvas.getContext('webgl2');
            if (!gl) return;

            function createShader(gl, type, source) {
                const s = gl.createShader(type);
                gl.shaderSource(s, source);
                gl.compileShader(s);
                return s;
            }

            const program = gl.createProgram();
            gl.attachShader(program, createShader(gl, gl.VERTEX_SHADER, vertexShaderSource));
            gl.attachShader(program, createShader(gl, gl.FRAGMENT_SHADER, fragmentShaderSource));
            gl.linkProgram(program);
            gl.useProgram(program);

            const locRes = gl.getUniformLocation(program, "u_resolution");
            const locTime = gl.getUniformLocation(program, "u_time");
            const locFXH = gl.getUniformLocation(program, "u_fixX_h");
            const locFYH = gl.getUniformLocation(program, "u_fixY_h");
            const locZoom = gl.getUniformLocation(program, "u_zoom");

            const buffer = gl.createBuffer();
            gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
            gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
            const pos = gl.getAttribLocation(program, "a_position");
            gl.enableVertexAttribArray(pos);
            gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);

            const startTime = Date.now();
            let currentZoomLog = 0;  // Start zoomed out
            let zoomDirection = 1.0; // Start zooming IN
            let targetZoomRate = 0.075;
            let actualZoomRate = 0.075;
            let deadSpaceTime = 0;

            function splitDouble(d) {
                const hi = Math.fround(d);
                const lo = d - hi;
                return [hi, lo];
            }

            // CPU probe to detect dead space
            function cpuIter(fx, fy, ux, uy) {
                let dx = ux, dy = uy;
                let max_iter = 180 + 45 * Math.log(Math.exp(currentZoomLog) + 1);
                if (max_iter > 750) max_iter = 750;
                for (let i = 0; i < max_iter; i++) {
                    let n_dx = 2 * (fx * dx - fy * dy) + (dx * dx - dy * dy);
                    let n_dy = 2 * (fx * dy + fy * dx) + 2 * dx * dy;
                    dx = n_dx; dy = n_dy;
                    if ((dx + fx) * (dx + fx) + (dy + fy) * (dy + fy) > 1024) return i;
                }
                return max_iter;
            }

            function render() {
                const now = Date.now();
                const time = (now - startTime) * 0.001;

                const dpr = window.devicePixelRatio || 1;
                if (canvas.width !== Math.floor(canvas.clientWidth * dpr)) {
                    canvas.width = Math.floor(canvas.clientWidth * dpr);
                    canvas.height = Math.floor(canvas.clientHeight * dpr);
                    gl.viewport(0, 0, canvas.width, canvas.height);
                }

                // Morphing Julia set constant
                const morphRate = 0.035;
                const phi = time * morphRate;
                const cx = 0.35 * Math.cos(phi) - 0.1 * Math.cos(2.0 * phi);
                const cy = 0.35 * Math.sin(phi) - 0.1 * Math.sin(2.0 * phi);
                const wx = 1.0 - 4.0 * cx;
                const wy = -4.0 * cy;
                const r_w = Math.sqrt(wx * wx + wy * wy);
                let sx = Math.sqrt((r_w + wx) * 0.5);
                let sy = Math.sqrt((r_w - wx) * 0.5);
                if (wy < 0.0) sy = -sy;
                let fixX = (1.0 + sx) * 0.5;
                let fixY = sy * 0.5;

                const zoom = Math.exp(currentZoomLog);
                
                // Probe for dead space
                const samples = [[0, 0], [0.1, 0.1], [-0.1, -0.1], [0.1, -0.1], [-0.1, 0.1]];
                let max_hits = 0;
                samples.forEach(s => {
                    let it = cpuIter(fixX, fixY, s[0] / zoom, s[1] / zoom);
                    if (it >= 745) max_hits++;
                });

                // Bounce logic - zoom out when dead space detected
                if (max_hits >= 5) {
                    deadSpaceTime += 0.016;
                    if (deadSpaceTime > 1.5) zoomDirection = -1.0;
                } else {
                    deadSpaceTime = 0;
                    if (zoomDirection < 0 && currentZoomLog < 2) zoomDirection = 1.0; // Resume zoom-in
                }

                actualZoomRate = actualZoomRate * 0.98 + (targetZoomRate * zoomDirection) * 0.02;
                currentZoomLog += actualZoomRate * 0.016;

                // Gentle pan
                const panRadius = 0.01 / zoom;
                fixX += panRadius * Math.cos(time * 0.15);
                fixY += panRadius * Math.sin(time * 0.15);

                gl.uniform2f(locRes, canvas.width, canvas.height);
                gl.uniform1f(locTime, time);
                gl.uniform2fv(locFXH, splitDouble(fixX));
                gl.uniform2fv(locFYH, splitDouble(fixY));
                gl.uniform2fv(locZoom, splitDouble(zoom));

                gl.drawArrays(gl.TRIANGLES, 0, 6);
                requestAnimationFrame(render);
            }
            requestAnimationFrame(render);
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
    music_dir = os.path.join(os.path.dirname(__file__), "Music")
    demo.launch(share=False, server_name="127.0.0.1", server_port=7860, theme=theme, css=css, js=js, allowed_paths=[music_dir])

