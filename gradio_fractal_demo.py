import gradio as gr
import os

# Custom CSS for glassmorphism and to ensure Gradio background is transparent
custom_css = """
body {
    background: transparent !important;
}

gradio-app {
    background: transparent !important;
}

.gradio-container {
    background: transparent !important;
}

/* Glassmorphism effect for blocks */
.prose, .form, .gr-box, .gr-panel, .gr-button {
    background: rgba(255, 255, 255, 0.05) !important;
    backdrop-filter: blur(10px) !important;
    -webkit-backdrop-filter: blur(10px) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 12px !important;
    color: #e0e0e0 !important;
}

/* Specific styling for clarity */
h1, h2, h3, p, label, .output-text {
    color: #ffffff !important;
    text-shadow: 0px 2px 4px rgba(0,0,0,0.5);
}

.gr-button {
    background: rgba(0, 255, 128, 0.2) !important;
    transition: all 0.3s ease;
}

.gr-button:hover {
    background: rgba(0, 255, 128, 0.4) !important;
    transform: translateY(-2px);
    box-shadow: 0 4px 15px rgba(0, 255, 128, 0.3);
}

input, textarea {
    background: rgba(0, 0, 0, 0.3) !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
    color: #ffffff !important;
}
"""

def process_text(text):
    return f"Processed: {text}"

# Path to the JS file
js_path = os.path.join(os.path.dirname(__file__), "fractal_shader.js")

with open(js_path, "r") as f:
    js_code = f.read()

with gr.Blocks() as demo:
    gr.Markdown("# 🌌 Fractal Background Demo")
    gr.Markdown("This UI features a high-performance WebGL fractal background and glassmorphism styling.")
    
    with gr.Row():
        input_text = gr.Textbox(label="Enter some text", placeholder="Type here...")
        output_text = gr.Textbox(label="Result")
    
    btn = gr.Button("Generate")
    btn.click(process_text, inputs=input_text, outputs=output_text)
    
    with gr.Accordion("How it works", open=False):
        gr.Markdown("""
        ### The Math
        This is a **Julia Set**, defined by the formula $z_{n+1} = z_n^2 + c$.
        
        ### The Animation
        The complex constant $c$ is animated over time, causing the fractal shape to morph and evolve continuously.
        
        ### The Tech
        - **WebGL/GLSL**: The animation runs directly on your GPU for maximum performance.
        - **Gradio**: Standard Gradio components are styled with `backdrop-filter: blur()` to create the glass effect.
        """)

if __name__ == "__main__":
    # Pass js and css here as per Gradio warning/updates
    demo.launch(js=js_code, css=custom_css)
