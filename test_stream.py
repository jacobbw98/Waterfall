
import ollama

client = ollama.Client()
model = "nemotron-3-nano:latest"

print(f"Testing {model} with STREAMING chat call...")
full_response = ""
for chunk in client.chat(model=model, messages=[{"role": "user", "content": "Hello"}], stream=True):
    content = chunk['message']['content']
    print(f"Chunk: {repr(content)}")
    full_response += content

print(f"\nFinal content: {repr(full_response)}")
