
import time
from typing import List, Dict, Any, Optional

class GoalTracker:
    """
    Manages the state and progress of the agent towards a defined goal.
    Helps detect loops and stalls in agent behavior.
    """
    def __init__(self, goal: str):
        self.goal = goal
        self.start_time = time.time()
        self.history: List[Dict[str, Any]] = []
        self.sub_goals: List[str] = []
        self.completed_steps: List[str] = []
        
        # Heuristics for loop detection
        self.last_actions: List[str] = []
        self.max_action_history = 5
        
    def add_action(self, tool_name: str, args: Dict[str, Any], result: str):
        """Record an action and its result."""
        action_summary = f"{tool_name}({args})"
        self.history.append({
            "timestamp": time.time(),
            "action": action_summary,
            "result": result[:500] # Cap size
        })
        
        self.last_actions.append(action_summary)
        if len(self.last_actions) > self.max_action_history:
            self.last_actions.pop(0)
            
    def check_for_loop(self) -> bool:
        """Detect if the agent is stuck in a repetitive loop."""
        if len(self.last_actions) < self.max_action_history:
            return False
        
        # Check if most recent actions are identical
        if all(a == self.last_actions[0] for a in self.last_actions):
            return True
        return False

    def get_progress_summary(self) -> str:
        """Generate a summary of what has been accomplished so far."""
        if not self.history:
            return "No actions taken yet."
        
        steps = [f"- {h['action']} -> Result: {h['result'][:100]}..." for h in self.history]
        return "\n".join(steps)

    def get_reflection_prompt(self, last_result: str) -> str:
        """Create a prompt for the agent to reflect on its progress."""
        history_summary = self.get_progress_summary()
        
        prompt = f"""### SELF-REFLECTION & PROGRESS CHECK
**LAST TOOL RESULT**: {last_result[:2000]}

**HISTORY OF ACTIONS**:
{history_summary}

**OBJECTIVE**: {self.goal}

**YOUR TASK**:
Review the objective and your history.
1. Have you achieved the goal?
2. If yes, provide the FINAL ANSWER.
3. If no, what is the SINGLE next step to get closer to the goal? 
Use a tool only if necessary. Avoid repeating failed actions.
"""
        return prompt
