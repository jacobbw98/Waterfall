
import ollama

client = ollama.Client()
model = "nemotron-3-nano:latest"

print(f"Testing {model} with MINIMAL chat call...")
response = client.chat(model=model, messages=[{"role": "user", "content": "Hello"}])
print(f"Response: {repr(response['message']['content'])}")
