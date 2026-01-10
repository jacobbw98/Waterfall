
import ollama

SYSTEM_PROMPT = "You are a helpful assistant."

client = ollama.Client()
model = "nemotron-3-nano:latest"

messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": "Hello, list the files in the current directory."}
]

options = {
    "num_predict": 1024,
    "temperature": 0.5,
    "top_p": 0.9,
}

print(f"Testing {model} WITH system prompt...")
response = client.chat(model=model, messages=messages)
print(f"Response WITH: {repr(response['message']['content'])}")

messages_no_sys = [{"role": "user", "content": "Hello, list the files in the current directory."}]
print(f"\nTesting {model} WITHOUT system prompt...")
response_no_sys = client.chat(model=model, messages=messages_no_sys)
print(f"Response WITHOUT: {repr(response_no_sys['message']['content'])}")
