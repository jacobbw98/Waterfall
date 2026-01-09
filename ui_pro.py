"""
Pro Agent UI - Split-screen with Thought Stream and Live Visual Feed.
"""
import gradio as gr
import base64
import os
import time
from agent import Agent
from ollama_client import list_models
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
            "error": "❌"
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
                if update["type"] == "response":
                    content = update["content"]
                    full_response = content
                    preview = content[:150].replace("\n", " ")
                    self.add_thought("thinking", preview + "...")
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
                    result_preview = update["result"][:150].replace("\n", " ")
                    self.add_thought("result", result_preview + "...")
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
        body_background_fill="linear-gradient(180deg, #0a0a1a 0%, #0d2040 50%, #0a1a30 100%)",
        body_background_fill_dark="linear-gradient(180deg, #0a0a1a 0%, #0d2040 50%, #0a1a30 100%)",
        block_background_fill="rgba(10, 25, 50, 0.9)",
        block_background_fill_dark="rgba(10, 25, 50, 0.9)",
        input_background_fill="rgba(15, 35, 60, 0.95)",
        input_background_fill_dark="rgba(15, 35, 60, 0.95)",
        button_primary_background_fill="linear-gradient(135deg, #1a5a8a, #2a7aaa)",
        button_primary_background_fill_dark="linear-gradient(135deg, #1a5a8a, #2a7aaa)",
    )
    
    with gr.Blocks(title="Pro AI Agent") as demo:
        # Custom CSS for matrix green and orange colors - NO WHITE
        gr.HTML("""
        <style>
        /* Remove all white backgrounds and borders */
        *, *::before, *::after {
            color: #00ff00 !important;
            border-color: #00ff00 !important;
        }
        
        /* Make all containers transparent */
        .block, .form, .panel, .container, .wrap, .gradio-container,
        .gr-box, .gr-form, .gr-panel, [class*="block"], [class*="container"] {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }
        
        /* Specific labeled elements - remove white box styling */
        label, .label-wrap {
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
        }
        
        /* Chat messages - dark green with green border */
        .chatbot, .chatbot * {
            color: #00ff00 !important;
            font-family: 'Consolas', 'Monaco', monospace !important;
            background: transparent !important;
        }
        
        .message, [class*="message"] {
            background: rgba(0, 30, 0, 0.6) !important;
            border: 1px solid #00ff00 !important;
            border-radius: 8px !important;
        }
        
        /* Input areas - dark with green border */
        textarea, input, .textbox, select {
            background: rgba(0, 20, 0, 0.8) !important;
            border: 1px solid #00ff00 !important;
            color: #00ff00 !important;
            font-family: 'Consolas', 'Monaco', monospace !important;
        }
        
        /* Message input - orange text */
        .gradio-textbox textarea, input[type="text"] {
            color: #ff8c00 !important;
        }
        
        /* Buttons - transparent with green border */
        button, .button, .btn {
            background: rgba(0, 50, 0, 0.5) !important;
            border: 1px solid #00ff00 !important;
            color: #00ff00 !important;
        }
        
        button:hover {
            background: rgba(0, 80, 0, 0.7) !important;
        }
        
        /* Image container - remove white background */
        .image-container, .upload-container, [class*="image"], img {
            background: transparent !important;
            border: 1px solid #00ff00 !important;
        }
        
        /* Dropdown */
        select, .dropdown, option {
            background: rgba(0, 20, 0, 0.9) !important;
            color: #00ff00 !important;
        }
        
        /* Remove SVG/icon white fills */
        svg, svg * {
            fill: #00ff00 !important;
            stroke: #00ff00 !important;
        }
        
        /* Checkbox - make it very visible */
        input[type="checkbox"] {
            accent-color: #00ff00 !important;
            width: 20px !important;
            height: 20px !important;
            border: 2px solid #00ff00 !important;
            background: rgba(0, 50, 0, 0.8) !important;
        }
        
        input[type="checkbox"]:checked {
            background: #00ff00 !important;
        }
        </style>
        """)
        
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
                    clear_btn = gr.Button("🗑️ Clear All")
                
                model_dropdown = gr.Dropdown(
                    choices=models,
                    value=models[0] if models else "nemotron-3-nano:latest",
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
        
        # Event handlers
        def on_send(message, history, model, planning):
            yield from ui.run_agent(message, history, model, planning)
        
        def on_clear():
            return ui.clear_all()
        
        def on_refresh():
            return ui.capture_screenshot()
        
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
    
    return demo, theme


if __name__ == "__main__":
    demo, theme = create_pro_ui()
    demo.launch(share=False, server_name="127.0.0.1", server_port=7860, theme=theme)

