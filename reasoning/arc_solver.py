"""
ARC-AGI Solver — powered by Poetiq's reasoning pipeline.

Wraps Poetiq's multi-attempt grid solver so the Waterfall agent can
delegate abstract reasoning / pattern-recognition tasks.

Configured to use Ollama models by default so everything stays local.
"""
import sys
import os
import json
import asyncio
from typing import Optional, List, Dict, Any

# Add vendor Poetiq to path
_poetiq_path = os.path.join(os.path.dirname(__file__), '..', 'vendor', 'poetiq-arc-agi-solver')
if os.path.isdir(_poetiq_path):
    sys.path.insert(0, os.path.abspath(_poetiq_path))

try:
    from arc_agi.solve import solve as poetiq_solve
    from arc_agi.io import build_kaggle_two_attempts
    from arc_agi.scoring import score_task
    POETIQ_AVAILABLE = True
except Exception as e:
    print(f"[ARCSolver] Failed to load Poetiq: {e}")
    POETIQ_AVAILABLE = False


class ARCSolver:
    """
    Abstract reasoning engine for grid/puzzle tasks.
    
    Uses Poetiq's multi-attempt coding solver pipeline adapted
    to run with local Ollama models.
    """
    
    def __init__(self, model: str = "nemotron-3-nano:latest"):
        """
        Initialize the ARC solver.
        
        Args:
            model: Ollama model to use (will be prefixed with 'ollama/' for LiteLLM)
        """
        self._model = model
        self._ollama_model = f"ollama/{model}" if not model.startswith("ollama/") else model
        self._available = POETIQ_AVAILABLE
        
        if self._available:
            self._patch_poetiq_for_ollama()
        else:
            print("[ARCSolver] WARNING: poetiq-arc-agi-solver not installed. "
                  "Run: pip install -r vendor/poetiq-arc-agi-solver/requirements.txt")
    
    @property
    def available(self) -> bool:
        return self._available
    
    def _patch_poetiq_for_ollama(self):
        """
        Patch Poetiq's LLM layer and config to use Ollama models.
        
        Poetiq uses LiteLLM which already supports ollama/ prefixes,
        we just need to add our model to the limiters and props dicts
        and update the config to point at our Ollama model.
        """
        try:
            from arc_agi import llm as poetiq_llm
            from arc_agi import config as poetiq_config
            from arc_agi.prompts import FEEDBACK_PROMPT, SOLVER_PROMPT_1
            
            # Dynamically import Limiter  
            try:
                from asynciolimiter import Limiter
            except ImportError:
                # Create a no-op limiter if asynciolimiter isn't installed
                class Limiter:
                    def __init__(self, rate):
                        pass
                    async def wait(self):
                        pass
            
            # Register our Ollama model in the LLM layer
            if self._ollama_model not in poetiq_llm.limiters:
                poetiq_llm.limiters[self._ollama_model] = Limiter(10.0)  # Higher rate for local
                poetiq_llm.props[self._ollama_model] = {}  # No special props for Ollama
            
            # Override the config to use our Ollama model
            poetiq_config.CONFIG_LIST = [
                {
                    'solver_prompt': SOLVER_PROMPT_1,
                    'feedback_prompt': FEEDBACK_PROMPT,
                    'llm_id': self._ollama_model,
                    'solver_temperature': 0.7,
                    'request_timeout': 5 * 60,  # 5 min timeout for local models
                    'max_total_timeouts': 5,
                    'max_total_time': None,
                    'per_iteration_retries': 2,
                    'num_experts': 1,
                    'max_iterations': 5,  # Fewer iterations for local models
                    'max_solutions': 3,
                    'selection_probability': 1.0,
                    'seed': 0,
                    'shuffle_examples': True,
                    'improving_order': True,
                    'return_best_result': True,
                    'use_new_voting': True,
                    'count_failed_matches': True,
                    'iters_tiebreak': False,
                    'low_to_high_iters': False,
                }
            ]
            
        except Exception as e:
            print(f"[ARCSolver] Warning: Could not patch Poetiq for Ollama: {e}")
    
    def solve(self, task_json: str) -> str:
        """
        Solve an ARC grid task.
        
        Args:
            task_json: JSON string with ARC task format:
                {
                    "train": [{"input": [[...]], "output": [[...]]}],
                    "test": [{"input": [[...]]}]
                }
                
        Returns:
            JSON string with predicted output grids, or error message
        """
        if not self._available:
            return "ARC solver unavailable: poetiq-arc-agi-solver not installed."
        
        try:
            task = json.loads(task_json) if isinstance(task_json, str) else task_json
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"
        
        # Extract train/test data
        train = task.get("train", [])
        test = task.get("test", [])
        
        if not train or not test:
            return "Task must have 'train' and 'test' fields with input/output grid pairs."
        
        train_in = [ex["input"] for ex in train]
        train_out = [ex["output"] for ex in train]
        test_in = [ex["input"] for ex in test]
        
        try:
            # Run the async solver
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
            
            if loop and loop.is_running():
                # We're already in an async context — use a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        poetiq_solve(train_in, train_out, test_in, problem_id="agent_task")
                    )
                    results = future.result(timeout=600)
            else:
                results = asyncio.run(
                    poetiq_solve(train_in, train_out, test_in, problem_id="agent_task")
                )
            
            # Build predictions
            kaggle_preds = build_kaggle_two_attempts(results, test_in)
            
            # Extract the best outputs
            output = {
                "predictions": kaggle_preds,
                "num_results": len(results),
                "status": "success"
            }
            
            # Score if test outputs are provided
            if test and "output" in test[0]:
                gt_outputs = [ex["output"] for ex in test]
                score = score_task(kaggle_preds, gt_outputs)
                output["score"] = score
                output["correct"] = score == 1.0
            
            return json.dumps(output, indent=2)
            
        except Exception as e:
            return f"ARC solver error: {e}"
    
    def solve_grid(
        self,
        train_inputs: List[List[List[int]]],
        train_outputs: List[List[List[int]]],
        test_inputs: List[List[List[int]]]
    ) -> str:
        """
        Solve an ARC task from pre-parsed grid data.
        
        Args:
            train_inputs: List of training input grids
            train_outputs: List of training output grids
            test_inputs: List of test input grids
            
        Returns:
            JSON string with predictions
        """
        task = {
            "train": [{"input": inp, "output": out} for inp, out in zip(train_inputs, train_outputs)],
            "test": [{"input": inp} for inp in test_inputs]
        }
        return self.solve(json.dumps(task))
