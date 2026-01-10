"""
Ollama Client - Wrapper for Ollama API with tool-calling support.
"""
import json
import ollama
from typing import Generator, Optional, Callable

DEFAULT_MODEL = "nemotron-3-nano:latest"

SYSTEM_PROMPT = """You are a highly capable agentic AI. Your objective is to achieve the USER GOAL autonomously by planning and executing actions.

### STRUCTURED OUTPUT PROTOCOL
1. **THINK**: Wrap your internal reasoning, step-by-step logic, and progress assessment in <think> tags. 
2. **ACT**: To use a tool, use: <tool_call>{"name": "tool_name", "arguments": {...}}</tool_call>
3. **FINAL ANSWER**: Only when ALL Success Criteria are met, provide a clear final summary OUTSIDE of all tags.

### OPERATIONAL FRAMEWORK
- **USER GOAL**: [Defined in Task]
- **SUCCESS CRITERIA**: [Defined in Task or inferred from Goal]
- **CONSTRAINTS**: 
    - Only call ONE tool at a time.
    - If a tool fails, analyze the error and try an alternative approach.
    - Do NOT provide intermediate chat unless a human takeover (wait_for_human) is required.
    - Continue until the Goal is fully achieved.

Available Tools:
- browser_navigate, browser_click, browser_type, browser_get_content, screenshot
- file_list, file_read, file_write
- game_focus_window, game_send_key
- wait_for_human (Use ONLY for captchas or manual logins)"""


class OllamaClient:
    """Client for interacting with Ollama API."""
    
    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self.client = ollama.Client()
        self.conversation_history = []
    
    def reset_conversation(self):
        """Clear conversation history."""
        self.conversation_history = []
    
    def chat(self, message: str, system_prompt: str = SYSTEM_PROMPT) -> str:
        """Send a message and get a response with retries for empty outputs."""
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": message})
        
        max_retries = 2
        assistant_message = ""
        
        for attempt in range(max_retries + 1):
            # Apply recommended parameters for Nemotron-3-Nano
            options = {
                "temperature": 0.6,
                "top_p": 0.95,
                "num_predict": 2048
            }
            
            response = self.client.chat(
                model=self.model,
                messages=messages,
                options=options
            )
            
            # Extract content - Nemotron often puts everything in 'thinking'
            raw_content = response["message"]["content"]
            thinking_content = response["message"].get("thinking", "")
            
            # If content is empty but thinking exists, use thinking as raw content
            # Wrap it in <think> tags so agent.py can parse it as a thought
            if not raw_content.strip() and thinking_content.strip():
                if attempt == 0:
                    print(f"[DEBUG] Found content in 'thinking' field ({len(thinking_content)} chars)")
                # If it doesn't already have tags, add them
                if "<think>" not in thinking_content:
                    raw_content = f"<think>{thinking_content}</think>"
                else:
                    raw_content = thinking_content
            elif raw_content.strip() and thinking_content.strip():
                # Both have content? Prepend thinking
                if "<think>" not in thinking_content:
                    raw_content = f"<think>{thinking_content}</think>\n{raw_content}"
                else:
                    raw_content = f"{thinking_content}\n{raw_content}"
            
            # Diagnostic log to terminal
            if attempt == 0 or len(raw_content) == 0:
                print(f"[DEBUG] Attempt {attempt+1} - Raw Length: {len(raw_content)}")
                if 0 < len(raw_content) < 200:
                    print(f"[DEBUG] Raw: {repr(raw_content)}")
            
            # We now return the RAW content (including <think> and <tool_call> tags)
            # The Agent class in agent.py handles the extraction and stripping for UI display.
            assistant_message = raw_content
            
            # Legacy cleanup: only remove "done thinking" strings if they appear outside tags
            if "...done thinking." in assistant_message:
                assistant_message = assistant_message.replace("...done thinking.", "").strip()
            
            if assistant_message.strip():
                break
            
            print(f"[DEBUG] Empty message on attempt {attempt+1}, retrying...")
        
        # Update conversation history
        self.conversation_history.append({"role": "user", "content": message})
        self.conversation_history.append({"role": "assistant", "content": assistant_message})
        
        return assistant_message
    
    def chat_stream(self, message: str, system_prompt: str = SYSTEM_PROMPT) -> Generator[str, None, None]:
        """Send a message and stream the response."""
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": message})
        
        full_response = ""
        
        for chunk in self.client.chat(
            model=self.model,
            messages=messages,
            stream=True
        ):
            content = chunk["message"]["content"]
            full_response += content
            yield content
        
        # Update conversation history after streaming completes
        self.conversation_history.append({"role": "user", "content": message})
        self.conversation_history.append({"role": "assistant", "content": full_response})
    
    def add_tool_result(self, tool_name: str, result: str):
        """Add a tool result to the conversation."""
        self.conversation_history.append({
            "role": "user",
            "content": f"Tool `{tool_name}` returned:\n```\n{result}\n```\n\nContinue with the task."
        })
    
    def parse_tool_call(self, response: str) -> Optional[dict]:
        """Extract tool call from response if present."""
        import re
        
        # Look for ```tool_call ... ``` blocks
        pattern = r"```tool_call\s*\n?(.*?)\n?```"
        match = re.search(pattern, response, re.DOTALL)
        
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                return None
        
        return None


def list_models() -> list[str]:
    """List available Ollama models."""
    client = ollama.Client()
    models_response = client.list()
    # Handle both dict and object responses based on library version
    if hasattr(models_response, 'models'):
        return [m.model for m in models_response.models]
    return [m.get("model") or m.get("name") for m in models_response.get("models", [])]


if __name__ == "__main__":
    # Quick test
    print("Available models:", list_models())
    client = OllamaClient()
    response = client.chat("Hello! What tools do you have available?")
    print("Response:", response)
