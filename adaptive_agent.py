"""
Adaptive Agent - Observe → Decide → Act
========================================

A computer automation agent that:
1. Takes a screenshot and understands what's on screen
2. Decides what to do next based on the current state and the goal
3. Executes the action
4. Observes again to see what changed and decides the next step

No predefined step sequences. No RL reward system.
Just: look at the screen → think → act → repeat.
"""

import os
import sys
import time
import json
import hashlib
import re
import subprocess
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

import pyautogui
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from visual_detector import VisualDetector, UIElement
from annotator import Annotator

try:
    import ollama
except ImportError:
    ollama = None


# ─── Data Structures ───────────────────────────────────────────────

@dataclass
class ScreenState:
    """What the agent sees right now."""
    screenshot_path: str
    annotated_path: str
    elements: List[Dict]
    element_count: int
    window_title: str
    screen_hash: str
    visible_text: str
    timestamp: float

    def describe(self, max_elements: int = 25) -> str:
        """Text description of what's on screen — fed to the LLM."""
        lines = [
            f"Active Window: {self.window_title}",
            f"UI Elements Found: {self.element_count}",
        ]
        if self.visible_text:
            lines.append(f"Visible Text: {self.visible_text[:300]}")

        interactive = {'button', 'input_field', 'link', 'checkbox', 'dropdown', 'icon'}
        sorted_elems = sorted(
            self.elements,
            key=lambda e: (0 if e.get('type') in interactive else 1, e.get('id', 0))
        )

        lines.append("\nUI Elements (interactive first):")
        for e in sorted_elems[:max_elements]:
            text = e.get('text', '').strip()
            etype = e.get('type', '?')
            eid = e.get('id', '?')
            cx, cy = e.get('center', (0, 0))
            if text:
                lines.append(f"  [{eid}] {etype} \"{text[:40]}\" at ({cx},{cy})")
            else:
                lines.append(f"  [{eid}] {etype} at ({cx},{cy})")

        if len(self.elements) > max_elements:
            lines.append(f"  ... +{len(self.elements) - max_elements} more")

        return "\n".join(lines)


@dataclass
class StepRecord:
    """What happened in one step."""
    step: int
    action_type: str
    action_detail: str
    params: Dict
    success: bool
    output: str
    screen_changed: bool
    elapsed: float


# ─── Screen Observer ───────────────────────────────────────────────

class Observer:
    """
    Fast screen observation using local CV (not LLM).
    Takes ~0.5-1.5s per observation.
    """

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.detector = VisualDetector(ocr_enabled=True)
        self.annotator = Annotator()
        self._count = 0

    def look(self) -> ScreenState:
        """Take a screenshot and understand what's on screen."""
        self._count += 1
        t0 = time.time()

        # Screenshot
        screenshot = pyautogui.screenshot()
        path = os.path.join(self.output_dir, f"screen_{self._count:03d}.png")
        screenshot.save(path)

        # Detect UI elements (CV-based, fast)
        elements = self.detector.detect(path, selective_ocr=True)
        element_dicts = [e.to_dict() if hasattr(e, 'to_dict') else e for e in elements]

        # Annotate
        ann_path = path.replace('.png', '_annotated.png')
        self.annotator.annotate(path, element_dicts, ann_path)

        # Active window
        window_title = self._get_window_title()

        # Screen hash for change detection
        small = cv2.resize(np.array(screenshot), (64, 64))
        screen_hash = hashlib.md5(small.tobytes()).hexdigest()

        # Collect visible text
        visible_text = " ".join(
            e.get('text', '') for e in element_dicts if e.get('text', '').strip()
        )[:500]

        elapsed = time.time() - t0
        print(f"   👁️  {len(element_dicts)} elements | {elapsed:.1f}s | Window: '{window_title}'")

        return ScreenState(
            screenshot_path=path,
            annotated_path=ann_path,
            elements=element_dicts,
            element_count=len(element_dicts),
            window_title=window_title,
            screen_hash=screen_hash,
            visible_text=visible_text,
            timestamp=time.time(),
        )

    def _get_window_title(self) -> str:
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value or "Unknown"
        except Exception:
            return "Unknown"


# ─── Action Executor ──────────────────────────────────────────────

class Executor:
    """Runs the actions the agent decides to take."""

    def run_command(self, command: str) -> Tuple[bool, str]:
        try:
            proc = subprocess.Popen(
                command, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )
            time.sleep(1.5)
            return True, f"Executed: {command} (PID: {proc.pid})"
        except Exception as e:
            return False, str(e)

    def click(self, x: int, y: int) -> Tuple[bool, str]:
        pyautogui.moveTo(x, y, duration=0.15)
        time.sleep(0.1)
        pyautogui.click()
        return True, f"Clicked ({x}, {y})"

    def type_text(self, text: str) -> Tuple[bool, str]:
        """Type text using clipboard for unicode reliability."""
        try:
            proc = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
            proc.communicate(text.encode('utf-16-le'))
            time.sleep(0.1)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.3)
            return True, f"Typed: '{text[:50]}'"
        except Exception:
            pyautogui.write(text, interval=0.02)
            return True, f"Typed: '{text[:50]}'"

    def hotkey(self, keys: List[str]) -> Tuple[bool, str]:
        pyautogui.hotkey(*keys, interval=0.05)
        return True, f"Pressed {'+'.join(keys)}"

    def scroll(self, direction: str = "down", amount: int = 3) -> Tuple[bool, str]:
        pyautogui.scroll(amount if direction == "up" else -amount)
        return True, f"Scrolled {direction}"


# ─── Decision Engine ──────────────────────────────────────────────

AGENT_PROMPT = """You are a computer automation agent. You look at the screen and decide what to do.

YOUR TASK: {task}

WHAT YOU'VE DONE SO FAR:
{history}

WHAT YOU SEE NOW:
{screen}

AVAILABLE ACTIONS (pick exactly one):
  COMMAND {{"command": "..."}}       — Run a shell command (open apps, scripts)
  CLICK {{"x": N, "y": N}}          — Click at screen coordinates
  TYPE {{"text": "..."}}             — Type text into the focused field
  HOTKEY {{"keys": ["ctrl", "n"]}}   — Press a key combination
  SCROLL {{"direction": "down"}}     — Scroll up or down
  WAIT {{"seconds": N}}             — Wait for something to load
  DONE {{}}                          — Task is finished

RULES:
- Look at the Active Window and Visible Text to understand what's happening.
- If the task says "open X" and X is already open, handle it (e.g. new file with Ctrl+N).
- If a dialog like "Save changes?" appears, dismiss it appropriately.
- After opening an app, make sure it's ready before typing.
- When you've completed the task AND verified it, use DONE.

RESPOND WITH EXACTLY:
THOUGHT: [1 sentence: what you see and why you're choosing this action]
ACTION: ACTION_NAME {{"param": "value"}}
"""


class DecisionEngine:
    """
    Asks the LLM: "Given what you see on screen, what should you do next?"
    The LLM sees the screen state as text (element list + window title + OCR text).
    """

    def __init__(self, model: str = "qwen3:0.6b", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host

    def decide(self, task: str, screen: ScreenState,
               history: List[StepRecord]) -> Tuple[str, Dict, str]:
        """
        Returns: (action_type, params, thought)
        """
        # Build history summary
        hist_lines = []
        if not history:
            hist_lines.append("  (nothing yet — this is the first step)")
        else:
            for h in history[-6:]:
                status = "✓" if h.success else "✗"
                changed = " [screen changed]" if h.screen_changed else ""
                hist_lines.append(f"  {h.step}. {h.action_type} → {status} {h.output[:60]}{changed}")

        prompt = AGENT_PROMPT.format(
            task=task,
            history="\n".join(hist_lines),
            screen=screen.describe(),
        )

        # Call LLM
        response = self._call_llm(prompt, screen.annotated_path)

        # Parse response
        return self._parse(response, screen)

    def _call_llm(self, prompt: str, image_path: str = None) -> str:
        if ollama is None:
            raise RuntimeError("ollama not installed")

        # Prepend /no_think for Qwen3 models to suppress <think> reasoning
        actual_prompt = prompt
        if 'qwen3' in self.model.lower() and 'vl' not in self.model.lower():
            actual_prompt = "/no_think\n" + prompt

        messages = [{"role": "user", "content": actual_prompt}]

        # Attach image for vision models
        if image_path and os.path.exists(image_path):
            vision_keywords = ['vl', 'llava', 'gemma3', 'minicpm', 'vision']
            if any(k in self.model.lower() for k in vision_keywords):
                messages[0]["images"] = [image_path]

        try:
            resp = ollama.chat(
                model=self.model,
                messages=messages,
                options={"temperature": 0.2, "num_predict": 300}
            )
            content = resp['message']['content']
            # Strip <think>...</think> blocks if present
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
            return content
        except Exception as e:
            print(f"   ⚠️ LLM error: {e}")
            return 'THOUGHT: LLM error.\nACTION: WAIT {"seconds": 1}'

    def _parse(self, response: str, screen: ScreenState,
               task: str = "", history: List[StepRecord] = None
               ) -> Tuple[str, Dict, str]:
        """Parse LLM response into (action_type, params, thought)."""
        thought = ""
        action_type = None
        params = {}

        for line in response.split('\n'):
            line = line.strip()
            if line.upper().startswith('THOUGHT:'):
                thought = line[8:].strip()

            if line.upper().startswith('ACTION:'):
                action_str = line[7:].strip()
                match = re.match(r'(\w+)\s*(\{.*\})?', action_str, re.DOTALL)
                if match:
                    action_type = match.group(1).upper()
                    if match.group(2):
                        try:
                            params = json.loads(match.group(2))
                        except json.JSONDecodeError:
                            params = {}

        # Resolve element_id → coordinates
        if action_type == "CLICK" and 'element_id' in params:
            eid = params['element_id']
            target = next((e for e in screen.elements if e.get('id') == eid), None)
            if target:
                params['x'] = target.get('center', (0, 0))[0]
                params['y'] = target.get('center', (0, 0))[1]

        # Normalizations
        if action_type in ('RUN', 'OPEN', 'CMD', 'EXEC'):
            action_type = 'COMMAND'
        elif action_type in ('WRITE', 'INPUT'):
            action_type = 'TYPE'
        elif action_type in ('KEY', 'SHORTCUT'):
            action_type = 'HOTKEY'
        elif action_type in ('COMPLETE', 'FINISH', 'FINISHED'):
            action_type = 'DONE'

        # FALLBACK: If LLM didn't produce a valid action, infer from task + history
        if not action_type or action_type == 'WAIT':
            inferred = self._infer_action(task, screen, history or [])
            if inferred:
                action_type, params, thought = inferred

        if not action_type:
            action_type = 'WAIT'
            params = {'seconds': 1}

        if not thought:
            thought = response.split('\n')[0][:80] if response else 'No response'

        return action_type, params, thought

    def _infer_action(self, task: str, screen: ScreenState,
                      history: List[StepRecord]) -> Optional[Tuple[str, Dict, str]]:
        """
        Smart fallback: infer the next action from task + current state + history.
        Used when the LLM fails to produce a clear action.
        """
        task_lower = task.lower()
        done_actions = {h.action_type for h in history}
        window = screen.window_title.lower()

        # Step 1: Need to open an app?
        app_map = {
            'notepad': 'notepad.exe', 'calculator': 'calc.exe',
            'paint': 'mspaint.exe', 'chrome': 'start chrome',
            'edge': 'start msedge', 'terminal': 'wt.exe',
        }
        for app_name, cmd in app_map.items():
            if app_name in task_lower:
                # Check if app is already open
                if app_name in window:
                    # App open — need new file? or type?
                    if 'type' in task_lower or 'write' in task_lower:
                        if 'TYPE' not in done_actions:
                            # Check if we need a new file first
                            if screen.visible_text and len(screen.visible_text.strip()) > 30:
                                if 'HOTKEY' not in done_actions:
                                    return 'HOTKEY', {'keys': ['ctrl', 'n']}, f'{app_name} has content, creating new file'
                            # Extract text to type
                            match = re.search(r'(?:type|write|enter)\s+["\']?(.+?)["\']?$', task_lower)
                            if match:
                                return 'TYPE', {'text': match.group(1)}, f'Typing into {app_name}'
                        else:
                            return 'DONE', {}, 'Text typed, task complete'
                    else:
                        return 'DONE', {}, f'{app_name} is open'
                else:
                    if 'COMMAND' not in done_actions:
                        return 'COMMAND', {'command': cmd}, f'Opening {app_name}'

        # Step 2: Need to type something?
        if ('type' in task_lower or 'write' in task_lower) and 'TYPE' not in done_actions:
            match = re.search(r'(?:type|write|enter)\s+["\']?(.+?)["\']?$', task_lower)
            if match:
                return 'TYPE', {'text': match.group(1)}, 'Typing text'

        # Step 3: Already done everything?
        if history and len(history) >= 2:
            if any(h.action_type == 'TYPE' and h.success for h in history):
                return 'DONE', {}, 'Task actions completed'
            if any(h.action_type == 'COMMAND' and h.success for h in history):
                if 'type' not in task_lower and 'write' not in task_lower:
                    return 'DONE', {}, 'App opened, task complete'

        return None


# ─── Adaptive Agent ────────────────────────────────────────────────

class AdaptiveAgent:
    """
    Observe → Decide → Act → Repeat.

    The agent looks at the screen, asks the LLM what to do,
    executes the action, and then looks again. No predefined plan.
    Each step is decided fresh based on what's currently on screen.
    """

    def __init__(self, model: str = "qwen3:0.6b",
                 host: str = "http://localhost:11434",
                 output_dir: str = "agent_output"):
        self.observer = Observer(output_dir)
        self.executor = Executor()
        self.engine = DecisionEngine(model, host)
        self.output_dir = output_dir
        self.history: List[StepRecord] = []

        os.makedirs(output_dir, exist_ok=True)
        print(f"🤖 Adaptive Agent ready (model={model})")

    def run(self, task: str, max_steps: int = 15) -> List[StepRecord]:
        """
        Execute a task by observing and deciding at each step.
        """
        print(f"\n{'='*65}")
        print(f"🎯 TASK: {task}")
        print(f"{'='*65}")

        self.history = []

        for step in range(1, max_steps + 1):
            print(f"\n{'─'*55}")
            print(f"Step {step}/{max_steps}")
            print(f"{'─'*55}")
            t0 = time.time()

            # 1. OBSERVE — look at the screen
            print("  👁️  Looking at screen...")
            screen = self.observer.look()

            # 2. DECIDE — ask the LLM what to do
            print("  🧠 Deciding next action...")
            action_type, params, thought = self.engine.decide(task, screen, self.history)

            print(f"     💭 {thought}")
            print(f"     ▶️  {action_type} {json.dumps(params)}")

            # 3. Check if done
            if action_type == "DONE":
                print(f"\n✅ Task complete!")
                self.history.append(StepRecord(
                    step=step, action_type="DONE",
                    action_detail=thought, params={},
                    success=True, output="Complete",
                    screen_changed=False, elapsed=time.time() - t0
                ))
                break

            # 4. ACT — execute the action
            success, output = self._execute(action_type, params)
            print(f"     {'✓' if success else '✗'} {output}")

            # 5. Wait for UI to settle, then check if screen changed
            settle = 2.0 if action_type == "COMMAND" else 0.5
            if action_type not in ("WAIT", "OBSERVE"):
                time.sleep(settle)

            after = self.observer.look()
            changed = screen.screen_hash != after.screen_hash

            if changed:
                print(f"     📸 Screen changed ✓")
            else:
                print(f"     📸 No visible change")

            # 6. Record
            self.history.append(StepRecord(
                step=step, action_type=action_type,
                action_detail=thought, params=params,
                success=success, output=output,
                screen_changed=changed, elapsed=time.time() - t0
            ))

        # Summary
        self._print_summary(task)
        self._save_log(task)
        return self.history

    def _execute(self, action_type: str, params: Dict) -> Tuple[bool, str]:
        """Execute a single action."""
        try:
            if action_type == "COMMAND":
                return self.executor.run_command(params.get('command', ''))
            elif action_type == "CLICK":
                return self.executor.click(params.get('x', 0), params.get('y', 0))
            elif action_type == "TYPE":
                return self.executor.type_text(params.get('text', ''))
            elif action_type == "HOTKEY":
                return self.executor.hotkey(params.get('keys', []))
            elif action_type == "SCROLL":
                return self.executor.scroll(params.get('direction', 'down'),
                                            params.get('amount', 3))
            elif action_type == "WAIT":
                time.sleep(params.get('seconds', 1.0))
                return True, f"Waited {params.get('seconds', 1.0)}s"
            else:
                return False, f"Unknown action: {action_type}"
        except Exception as e:
            return False, str(e)

    def _print_summary(self, task: str):
        print(f"\n{'='*65}")
        print(f"📋 SUMMARY")
        print(f"{'='*65}")
        print(f"Task: {task}")
        print(f"Steps: {len(self.history)}")
        total = sum(h.elapsed for h in self.history)
        print(f"Time: {total:.1f}s\n")

        for h in self.history:
            s = "✓" if h.success else "✗"
            c = "↻" if h.screen_changed else " "
            print(f"  {h.step}. [{s}]{c} {h.action_type:10s} {h.output[:50]}")

    def _save_log(self, task: str):
        log = {
            "task": task,
            "steps": len(self.history),
            "total_time": sum(h.elapsed for h in self.history),
            "actions": [{
                "step": h.step,
                "action": h.action_type,
                "params": h.params,
                "thought": h.action_detail,
                "success": h.success,
                "output": h.output,
                "screen_changed": h.screen_changed,
                "time": round(h.elapsed, 2),
            } for h in self.history]
        }
        path = os.path.join(self.output_dir, "session.json")
        with open(path, 'w') as f:
            json.dump(log, f, indent=2)
        print(f"\n💾 Session log: {path}")


# ─── CLI ───────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Adaptive Agent — Observe → Decide → Act")
    parser.add_argument("task", nargs="?", default="Open Notepad and type Hello World")
    parser.add_argument("--model", default="qwen3:0.6b", help="Ollama model name")
    parser.add_argument("--vision-model", default=None,
                       help="Use a separate vision model (e.g. qwen3-vl:2b) for decisions")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--max-steps", type=int, default=15)
    parser.add_argument("--output", default="agent_output")
    args = parser.parse_args()

    model = args.vision_model or args.model

    agent = AdaptiveAgent(
        model=model,
        host=args.host,
        output_dir=args.output,
    )
    history = agent.run(args.task, max_steps=args.max_steps)
    sys.exit(0 if any(h.action_type == "DONE" for h in history) else 1)


if __name__ == "__main__":
    main()
