"""
Agent - Main agentic loop with tool execution.
"""
import json
import re
from typing import Dict, Any, Callable, Optional, Generator
from ollama_client import OllamaClient, SYSTEM_PROMPT
from tools.browser import get_browser
from tools.filesystem import get_filesystem
from tools.grading import get_grading
from tools.gamecontrol import get_gamecontrol
from tools.vision import get_vision


class Agent:
    """Agentic AI with tool-calling capabilities."""
    
    def __init__(self, model: str = "nemotron-3-nano:latest"):
        self.client = OllamaClient(model)
        self.tools = self._register_tools()
        self.max_iterations = 10
        self.verbose = True
    
    def _register_tools(self) -> Dict[str, Callable]:
        """Register all available tools."""
        browser = get_browser()
        fs = get_filesystem()
        grading = get_grading()
        game = get_gamecontrol()
        vision = get_vision()
        
        return {
            # Browser tools
            "browser_navigate": lambda url: browser.navigate(url),
            "browser_click": lambda selector=None, x=None, y=None: browser.click(selector, x, y),
            "browser_type": lambda text, selector=None: browser.type_text(text, selector),
            "browser_press_key": lambda key: browser.press_key(key),
            "browser_screenshot": lambda: browser.screenshot(),
            "browser_get_content": lambda: browser.get_content(),
            
            # File system tools
            "file_read": lambda path: fs.read_file(path),
            "file_write": lambda path, content: fs.write_file(path, content),
            "file_list": lambda path: fs.list_directory(path),
            "file_search": lambda directory, pattern: fs.search_files(directory, pattern),
            
            # Grading tools
            "list_rubrics": lambda: grading.list_rubrics(),
            "load_rubric": lambda rubric_name: grading.load_rubric(rubric_name),
            "grade_submission": lambda submission_path, rubric_name: grading.grade_submission(submission_path, rubric_name),
            
            # Game control tools
            "game_list_windows": lambda: game.list_windows(),
            "game_focus_window": lambda window_title: game.focus_window(window_title),
            "game_send_key": lambda key, hold_time=0: game.send_key(key, hold_time),
            "game_send_keys": lambda keys: game.send_keys(keys),
            "game_send_hotkey": lambda *keys: game.send_hotkey(*keys),
            "game_move_mouse": lambda x, y, relative=False: game.move_mouse(x, y, relative),
            "game_click": lambda x=None, y=None, button='left', clicks=1: game.click_mouse(x, y, button, clicks),
            "game_scroll": lambda amount: game.scroll(amount),
            "game_screenshot": lambda: game.screenshot(),
            "game_pixel_color": lambda x, y: game.get_pixel_color(x, y),
            
            # Vision tools
            "screenshot": lambda: vision.save_screenshot("screenshot.png"),
            
            # Human interaction tools
            "wait_for_human": lambda reason="": f"HUMAN_TAKEOVER_REQUESTED: {reason}",
        }
    
    def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Execute a tool and return the result, ignoring unexpected arguments."""
        if tool_name not in self.tools:
            return f"Error: Unknown tool '{tool_name}'"
        
        try:
            import inspect
            tool_fn = self.tools[tool_name]
            
            # Intelligently filter arguments to match what the tool actually accepts
            # This handles models hallucinating extra arguments (like 'url' for browser_get_content)
            sig = inspect.signature(tool_fn)
            params = sig.parameters
            
            # If the tool takes **kwargs, we can pass everything
            if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
                filtered_args = args
            else:
                # Otherwise, only pass what's in the signature
                filtered_args = {k: v for k, v in args.items() if k in params}
                
                # Check for positional-only arguments (rare in our lambdas but good to have)
                # Our tools are mostly lambdas with keyword support, so this simplified filtering is usually enough
            
            result = tool_fn(**filtered_args)
            return str(result)
        except Exception as e:
            return f"Error executing {tool_name}: {e}"
    
    def parse_tool_call(self, response: str) -> Optional[Dict]:
        """Extract tool call from response using XML tags or markdown fallback."""
        # 1. Try to find <tool_call> ... </tool_call> blocks (Official NVIDIA protocol)
        xml_pattern = r"<tool_call>\s*\n?(.*?)\n?</tool_call>"
        xml_match = re.search(xml_pattern, response, re.DOTALL)
        
        json_content = None
        if xml_match:
            json_content = xml_match.group(1).strip()
        else:
            # 2. Markdown fallback: Try to find ```tool_call ... ``` blocks
            md_pattern = r"```tool_call\s*\n?(.*?)\n?```"
            md_match = re.search(md_pattern, response, re.DOTALL)
            if md_match:
                json_content = md_match.group(1).strip()
            else:
                # 3. Last resort: Look for any JSON-like object
                json_pattern = r"\{.*\}"
                json_match = re.search(json_pattern, response, re.DOTALL)
                if json_match:
                    json_content = json_match.group(0).strip()

        if json_content:
            try:
                data = json.loads(json_content)
                
                # Normalize format: Support {"tool": "...", "args": {}} 
                # AND NVIDIA/OpenAI style {"name": "...", "arguments": {}}
                tool_name = data.get("tool") or data.get("name")
                tool_args = data.get("args") or data.get("arguments") or {}
                
                if tool_name:
                    return {"tool": tool_name, "args": tool_args}
                    
                # Nested OpenAI style {"tool_calls": [...]}
                if "tool_calls" in data and isinstance(data["tool_calls"], list):
                    call = data["tool_calls"][0]
                    nested_name = call.get("name") or call.get("function", {}).get("name")
                    nested_args = call.get("arguments") or call.get("function", {}).get("arguments") or {}
                    if nested_name:
                        return {"tool": nested_name, "args": nested_args}
                        
            except json.JSONDecodeError:
                pass
        
        # 4. NATURAL LANGUAGE EXTRACTION: Try to extract tool intent from plain English
        # E.g. "use browser_navigate with url https://example.com"
        nl_patterns = [
            # browser_navigate patterns
            (r"(?:use|call)\s+browser_navigate\s+(?:to|with\s+url\s+)?[\"']?(https?://[^\s\"']+)[\"']?",
             lambda m: {"tool": "browser_navigate", "args": {"url": m.group(1)}}),
            (r"navigate\s+to\s+[\"']?(https?://[^\s\"']+)[\"']?",
             lambda m: {"tool": "browser_navigate", "args": {"url": m.group(1)}}),
            (r"go\s+to\s+[\"']?(https?://[^\s\"']+)[\"']?",
             lambda m: {"tool": "browser_navigate", "args": {"url": m.group(1)}}),
            # browser_get_content
            (r"(?:use|call)\s+browser_get_content",
             lambda m: {"tool": "browser_get_content", "args": {}}),
            (r"get\s+(?:page\s+)?content",
             lambda m: {"tool": "browser_get_content", "args": {}}),
            # screenshot
            (r"(?:take|get|use)\s+screenshot",
             lambda m: {"tool": "screenshot", "args": {}}),
        ]
        
        for pattern, extractor in nl_patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                return extractor(match)
                
        return None
    
    def run(self, task: str) -> Generator[Dict[str, Any], None, None]:
        """
        Run the agent loop for a task.
        Yields status updates for each step.
        """
        from goal_tracker import GoalTracker
        tracker = GoalTracker(task)
        
        self.client.reset_conversation()
        yield {"type": "start", "task": task}
        
        # Initial model prompt - direct action, not planning
        current_prompt = f"USER GOAL: {task}\n\nStart now. Call the first tool you need, or answer directly if no tools are required."
        iteration = 0
        last_tool_result = ""
        last_tool_name = ""
        
        while iteration < self.max_iterations:
            # Get response from LLM
            response = self.client.chat(current_prompt)
            if self.verbose:
                print(f"[DEBUG] Iteration {iteration} Raw: {response[:200]}...")
            
            # 1. Extract and yield thoughts (<think> tags)
            think_match = re.search(r"<think>(.*?)</think>", response, re.DOTALL)
            if think_match:
                thought = think_match.group(1).strip()
                if thought:
                    yield {"type": "thought", "content": thought}
            
            # 2. Extract content outside of tags
            clean_content = re.sub(r"<(think|tool_call)>.*?</\1>", "", response, flags=re.DOTALL).strip()
            # Also clean markdown versions
            clean_content = re.sub(r"```tool_call.*?```", "", clean_content, flags=re.DOTALL).strip()
            
            # 3. Check for tool call
            tool_call = self.parse_tool_call(response)
            
            if not tool_call:
                # No tool call - but is this actually a final answer or an incomplete response?
                
                # DETECT INCOMPLETE RESPONSES: Model says it will do something but didn't include tool call
                # Also detect meta-reasoning about format (model confused about HOW to respond)
                incomplete_patterns = [
                    r"(?:first|next|now)\s+(?:step|I\s+will|I'll|let me|I\s+need)",
                    r"^(?:so\s+)?(?:first|let me|I will|I'll|I need to|I should|I'm going to)",
                    r"plan(?:ning)?\s+(?:my\s+)?approach",
                    r"(?:will|going to|need to)\s+(?:use|call|try|execute)\s+(?:the\s+)?(?:tool|browser|file)",
                    r"^step\s+\d+:",
                    r"my approach (?:is|will be)",
                    # Meta-reasoning about format (model is confused)
                    r"(?:THINK|THINKING)\s*(?:tag|with|using)",
                    r"produce\s+(?:THINK|FINAL|response)",
                    r"(?:inside|outside)\s+(?:the\s+)?(?:tag|think)",
                    r"response\s+format",
                    r"we\s+(?:can|should|need to)\s+(?:respond|output|produce)",
                    r"per\s+instructions",
                    # Natural language tool descriptions (model says what tool but doesn't call it)
                    r"(?:use|call|try)\s+browser_",
                    r"(?:use|call|try)\s+file_",
                    r"(?:use|call|try)\s+game_",
                    r"(?:use|call|try)\s+screenshot",
                    r"we(?:'ll)?\s+need\s+to",
                    r"likely\s+(?:we|I)\s+need",
                    r"then\s+(?:maybe\s+)?browser_",
                    r"fetch\s+content\s+first",
                ]
                
                is_incomplete = False
                if clean_content:
                    for pattern in incomplete_patterns:
                        if re.search(pattern, clean_content, re.IGNORECASE):
                            is_incomplete = True
                            break
                
                if is_incomplete:
                    # Model intended to continue but didn't include a tool call
                    # Prompt it to actually execute
                    yield {"type": "thought", "content": f"(Model said: {clean_content})"}
                    current_prompt = (
                        "STOP PLANNING. Execute now.\n"
                        "Example: <tool_call>{\"name\": \"browser_navigate\", \"arguments\": {\"url\": \"https://example.com\"}}</tool_call>\n"
                        "Or just write your answer if no tool is needed."
                    )
                    iteration += 1
                    continue
                
                # Check if the model put its FINAL ANSWER inside <think> tags
                # This is a common pattern with Nemotron's native thinking mode
                final_answer = None
                if think_match:
                    thought = think_match.group(1).strip()
                    # Look for "FINAL ANSWER:" pattern in thinking
                    final_patterns = [
                        r"FINAL ANSWER[:\s]*(.+?)(?:$|\n\n)",
                        r"Thus[,:\s]+(?:the )?(?:final )?(?:answer|response|result)[:\s]*(.+?)(?:$|\n\n)",
                        r"(?:In conclusion|Therefore|To summarize)[,:\s]*(.+?)(?:$|\n\n)"
                    ]
                    for pattern in final_patterns:
                        match = re.search(pattern, thought, re.IGNORECASE | re.DOTALL)
                        if match:
                            final_answer = match.group(1).strip()
                            # Clean up any trailing protocol instructions
                            final_answer = re.sub(r"\s*Use THINK to plan.*$", "", final_answer, flags=re.IGNORECASE)
                            if len(final_answer) > 10:  # Only use if substantial
                                break
                            else:
                                final_answer = None
                
                if clean_content:
                    yield {"type": "response", "content": clean_content}
                
                # Determine final text with priority: clean_content > extracted final_answer > tool result > fallback
                final_text = clean_content
                if not final_text and final_answer:
                    final_text = final_answer
                if not final_text:
                    if last_tool_result:
                        final_text = f"Goal achieved using {last_tool_name}. Final status:\n\n{last_tool_result[:1500]}"
                    else:
                        # Last resort: summarize from the thought if available
                        if think_match:
                            thought = think_match.group(1).strip()
                            # Take the last substantial sentence as summary
                            sentences = [s.strip() for s in thought.split('.') if len(s.strip()) > 20]
                            if sentences:
                                final_text = sentences[-1] + "."
                        if not final_text:
                            final_text = "Goal achieved. See the thought stream for details."
                
                yield {"type": "complete", "final_response": final_text}
                break
            
            # 4. If there is content + a tool call, show the content as a response
            if clean_content:
                yield {"type": "response", "content": clean_content}
            
            # 5. Execute tool
            tool_name = tool_call.get("tool", "")
            tool_args = tool_call.get("args", {})
            
            yield {"type": "tool_call", "tool": tool_name, "args": tool_args}
            
            result = self.execute_tool(tool_name, tool_args)
            tracker.add_action(tool_name, tool_args, result)
            
            last_tool_result = result
            last_tool_name = tool_name
            yield {"type": "tool_result", "tool": tool_name, "result": result}
            
            # 6. REFLECT: Feed result back and continue loop with a progress check
            self.client.add_tool_result(tool_name, result)
            
            # Check for looping behavior
            if tracker.check_for_loop():
                current_prompt = f"LOOP DETECTED: You have called {tool_name} with identical arguments multiple times. Please try a DIFFERENT approach or check if the goal is already met."
            else:
                current_prompt = tracker.get_reflection_prompt(result)
            
            iteration += 1
        
        if iteration >= self.max_iterations:
            yield {"type": "max_iterations", "message": "Reached maximum iterations"}
    
    def run_sync(self, task: str) -> str:
        """Run the agent and return the final response."""
        final = ""
        for update in self.run(task):
            if self.verbose:
                print(f"[{update['type']}]", update.get('content', update.get('result', '')))
            if update["type"] == "complete":
                final = update["final_response"]
            elif update["type"] == "max_iterations":
                final = update["message"]
        return final


if __name__ == "__main__":
    # Quick test
    agent = Agent()
    result = agent.run_sync("List the files in the current directory.")
    print("\n=== FINAL RESULT ===")
    print(result)
