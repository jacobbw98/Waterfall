
import requests
import json

url = "http://localhost:11434/api/chat"
model = "nemotron-3-nano:latest"

system_prompt = """You are a helpful AI assistant. 
IMPORTANT: Always use the following XML tags for structured output:
1. Wrap your internal reasoning and step-by-step thinking in <think> tags BEFORE any tool call or final response.
2. To use a tool, you MUST use the following format:
<tool_call>
{"name": "tool_name", "arguments": {"arg1": "value"}}
</tool_call>"""

payload = {
    "model": model,
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "summarize the front page of reddit"}
    ],
    "stream": False
}

print(f"Testing {model} via RAW HTTP request...")
try:
    response = requests.post(url, json=payload)
    print(f"Status: {response.status_code}")
    print(f"Full JSON: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")
