"""
Grounding Agent - ACI (Agent-Computer Interface)
Translates natural language descriptions into screen coordinates and actions.
"""

import re
import logging
from io import BytesIO
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

import pyautogui
from PIL import Image
import pytesseract
from pytesseract import Output

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.mllm import LMMAgent
from memory.procedural_memory import PROCEDURAL_MEMORY

logger = logging.getLogger(__name__)


def agent_action(func):
    """Decorator to mark functions as agent actions."""
    func.is_agent_action = True
    return func


class ACI:
    """Base Agent-Computer Interface."""
    
    def __init__(self):
        self.notes: List[str] = []


class OSWorldACI(ACI):
    """
    OSWorld ACI - Grounding agent for UI interactions.
    
    This class provides methods to:
    - Generate coordinates from natural language descriptions
    - Extract text from screenshots (OCR)
    - Perform UI actions (click, type, scroll, drag, etc.)
    """
    
    def __init__(self, 
                 env=None,
                 platform: str = "windows",
                 engine_params_for_generation: Optional[Dict] = None,
                 engine_params_for_grounding: Optional[Dict] = None,
                 width: int = 1920,
                 height: int = 1080,
                 code_agent_budget: int = 20):
        """
        Initialize OSWorld ACI.
        
        Args:
            env: Environment controller for code execution
            platform: OS platform (darwin, linux, windows)
            engine_params_for_generation: LLM params for text generation
            engine_params_for_grounding: LLM params for visual grounding
            width: Screen width
            height: Screen height
            code_agent_budget: Max steps for code agent
        """
        super().__init__()
        
        self.env = env
        self.platform = platform.lower()
        self.width = width
        self.height = height
        
        # Screenshot observation
        self.obs: Optional[Dict] = None
        self.current_task_instruction: Optional[str] = None
        self.last_code_agent_result: Optional[Dict] = None
        
        # Initialize grounding model
        if engine_params_for_grounding:
            self.grounding_model = LMMAgent(engine_params_for_grounding)
            self.engine_params_for_grounding = engine_params_for_grounding
        else:
            self.grounding_model = None
            self.engine_params_for_grounding = {}
        
        # Initialize text span agent
        if engine_params_for_generation:
            self.text_span_agent = LMMAgent(
                engine_params=engine_params_for_generation,
                system_prompt=PROCEDURAL_MEMORY.PHRASE_TO_WORD_COORDS_PROMPT
            )
        else:
            self.text_span_agent = None
    
    def assign_screenshot(self, obs: Dict):
        """Assign current screenshot observation."""
        self.obs = obs
    
    def set_task_instruction(self, task_instruction: str):
        """Set current task instruction."""
        self.current_task_instruction = task_instruction
    
    def generate_coords(self, ref_expr: str, obs: Optional[Dict] = None) -> List[int]:
        """
        Generate (x, y) coordinates from natural language reference.
        
        Args:
            ref_expr: Natural language description (e.g., "the search button")
            obs: Observation dict with screenshot
            
        Returns:
            [x, y] coordinates
        """
        if obs is None:
            obs = self.obs
        
        if self.grounding_model is None:
            logger.warning("No grounding model available, returning center")
            return [self.width // 2, self.height // 2]
        
        # Reset grounding model
        self.grounding_model.reset()
        
        # Create prompt
        prompt = f"Query:{ref_expr}\nOutput only the coordinate of one point in your response.\n"
        
        self.grounding_model.add_message(
            text_content=prompt,
            image_content=obs.get("screenshot"),
            put_text_last=True
        )
        
        # Generate response
        try:
            response = self.grounding_model.get_response(temperature=0.0)
            logger.info(f"Grounding response: {response}")
            
            # Extract coordinates
            numericals = re.findall(r"\d+", response)
            if len(numericals) >= 2:
                coords = [int(numericals[0]), int(numericals[1])]
                return self.resize_coordinates(coords)
            else:
                logger.warning(f"Could not parse coordinates from: {response}")
                return [self.width // 2, self.height // 2]
        except Exception as e:
            logger.error(f"Error generating coordinates: {e}")
            return [self.width // 2, self.height // 2]
    
    def get_ocr_elements(self, image_data: bytes) -> Tuple[str, List[Dict]]:
        """
        Extract text elements from image using OCR.
        
        Args:
            image_data: Image bytes
            
        Returns:
            (ocr_table_string, list_of_elements)
        """
        try:
            image = Image.open(BytesIO(image_data))
            image_data_dict = pytesseract.image_to_data(image, output_type=Output.DICT)
            
            # Clean text
            for i, word in enumerate(image_data_dict["text"]):
                image_data_dict["text"][i] = re.sub(
                    r"^[^a-zA-Z\s.,!?;:\-\+]+|[^a-zA-Z\s.,!?;:\-\+]+$", "", word
                )
            
            ocr_elements = []
            ocr_table = "Text Table:\nWord id\tText\n"
            grouping_map = defaultdict(list)
            ocr_id = 0
            
            for i in range(len(image_data_dict["text"])):
                block_num = image_data_dict["block_num"][i]
                if image_data_dict["text"][i]:
                    grouping_map[block_num].append(image_data_dict["text"][i])
                    ocr_table += f"{ocr_id}\t{image_data_dict['text'][i]}\n"
                    ocr_elements.append({
                        "id": ocr_id,
                        "text": image_data_dict["text"][i],
                        "group_num": block_num,
                        "word_num": len(grouping_map[block_num]),
                        "left": image_data_dict["left"][i],
                        "top": image_data_dict["top"][i],
                        "width": image_data_dict["width"][i],
                        "height": image_data_dict["height"][i]
                    })
                    ocr_id += 1
            
            return ocr_table, ocr_elements
            
        except Exception as e:
            logger.error(f"OCR error: {e}")
            return "Text Table:\nWord id\tText\n", []
    
    def generate_text_coords(self, phrase: str, obs: Optional[Dict] = None, 
                            alignment: str = "") -> List[int]:
        """
        Generate coordinates for text phrase.
        
        Args:
            phrase: Text to find
            obs: Observation with screenshot
            alignment: "start" for first word, "end" for last word
            
        Returns:
            [x, y] coordinates
        """
        if obs is None:
            obs = self.obs
        
        if self.text_span_agent is None:
            return [self.width // 2, self.height // 2]
        
        # Get OCR elements
        ocr_table, ocr_elements = self.get_ocr_elements(obs.get("screenshot", b""))
        
        if not ocr_elements:
            return [self.width // 2, self.height // 2]
        
        # Create alignment prompt
        alignment_prompt = ""
        if alignment == "start":
            alignment_prompt = "**Important**: Output the word id of the FIRST word in the provided phrase.\n"
        elif alignment == "end":
            alignment_prompt = "**Important**: Output the word id of the LAST word in the provided phrase.\n"
        
        # Query LLM
        self.text_span_agent.reset()
        self.text_span_agent.add_message(
            alignment_prompt + "Phrase: " + phrase + "\n" + ocr_table,
            role="user"
        )
        self.text_span_agent.add_message(
            "Screenshot:\n",
            image_content=obs.get("screenshot"),
            role="user"
        )
        
        try:
            response = self.text_span_agent.get_response(temperature=0.0)
            numericals = re.findall(r"\d+", response)
            
            if numericals:
                text_id = int(numericals[-1])
                if 0 <= text_id < len(ocr_elements):
                    elem = ocr_elements[text_id]
                    
                    # Calculate coordinates based on alignment
                    if alignment == "start":
                        return [elem["left"], elem["top"] + elem["height"] // 2]
                    elif alignment == "end":
                        return [elem["left"] + elem["width"], elem["top"] + elem["height"] // 2]
                    else:
                        return [elem["left"] + elem["width"] // 2, 
                               elem["top"] + elem["height"] // 2]
        except Exception as e:
            logger.error(f"Text grounding error: {e}")
        
        return [self.width // 2, self.height // 2]
    
    def resize_coordinates(self, coordinates: List[int]) -> List[int]:
        """Resize coordinates from grounding model resolution to screen resolution."""
        grounding_width = self.engine_params_for_grounding.get("grounding_width", self.width)
        grounding_height = self.engine_params_for_grounding.get("grounding_height", self.height)
        
        if grounding_width == self.width and grounding_height == self.height:
            return coordinates
        
        return [
            round(coordinates[0] * self.width / grounding_width),
            round(coordinates[1] * self.height / grounding_height)
        ]
    
    # ============== Agent Actions ==============
    
    @agent_action
    def click(self, element_description: str, num_clicks: int = 1, 
              button_type: str = "left", hold_keys: List[str] = None) -> str:
        """
        Click on an element.
        
        Args:
            element_description: Natural language description of element
            num_clicks: Number of clicks
            button_type: "left", "right", or "middle"
            hold_keys: Keys to hold while clicking
        """
        hold_keys = hold_keys or []
        coords = self.generate_coords(element_description, self.obs)
        x, y = coords
        
        command = "import pyautogui; "
        
        for k in hold_keys:
            command += f"pyautogui.keyDown({repr(k)}); "
        
        command += f"pyautogui.click({x}, {y}, clicks={num_clicks}, button={repr(button_type)}); "
        
        for k in hold_keys:
            command += f"pyautogui.keyUp({repr(k)}); "
        
        return command
    
    @agent_action
    def type(self, element_description: Optional[str] = None, text: str = "",
             overwrite: bool = False, enter: bool = False) -> str:
        """
        Type text into an element.
        
        Args:
            element_description: Element to type into (None for current focus)
            text: Text to type
            overwrite: Whether to clear existing text first
            enter: Whether to press Enter after typing
        """
        command = "import pyautogui; "
        
        # Click on element if specified
        if element_description:
            coords = self.generate_coords(element_description, self.obs)
            x, y = coords
            command += f"pyautogui.click({x}, {y}); "
        
        # Clear existing text if requested
        if overwrite:
            ctrl_key = "command" if self.platform == "darwin" else "ctrl"
            command += f"pyautogui.hotkey({repr(ctrl_key)}, 'a'); "
            command += "pyautogui.press('backspace'); "
        
        # Type text (handle unicode)
        has_unicode = any(ord(char) > 127 for char in text)
        
        if has_unicode:
            command += f"pyautogui.write({repr(text)}); "
        else:
            command += f"pyautogui.typewrite({repr(text)}, interval=0.01); "
        
        if enter:
            command += "pyautogui.press('enter'); "
        
        return command
    
    @agent_action
    def scroll(self, element_description: str, clicks: int, 
               shift: bool = False) -> str:
        """
        Scroll at an element location.
        
        Args:
            element_description: Element to scroll at
            clicks: Number of clicks (positive=up, negative=down)
            shift: Whether to use shift+scroll for horizontal
        """
        coords = self.generate_coords(element_description, self.obs)
        x, y = coords
        
        if shift:
            return f"import pyautogui; pyautogui.moveTo({x}, {y}); pyautogui.hscroll({clicks})"
        else:
            return f"import pyautogui; pyautogui.moveTo({x}, {y}); pyautogui.scroll({clicks})"
    
    @agent_action
    def drag_and_drop(self, starting_description: str, ending_description: str,
                      hold_keys: List[str] = None) -> str:
        """
        Drag from one element to another.
        
        Args:
            starting_description: Starting element
            ending_description: Ending element
            hold_keys: Keys to hold while dragging
        """
        hold_keys = hold_keys or []
        
        coords1 = self.generate_coords(starting_description, self.obs)
        coords2 = self.generate_coords(ending_description, self.obs)
        x1, y1 = coords1
        x2, y2 = coords2
        
        command = "import pyautogui; "
        command += f"pyautogui.moveTo({x1}, {y1}); "
        
        for k in hold_keys:
            command += f"pyautogui.keyDown({repr(k)}); "
        
        command += f"pyautogui.dragTo({x2}, {y2}, duration=0.5, button='left'); "
        command += "pyautogui.mouseUp(); "
        
        for k in hold_keys:
            command += f"pyautogui.keyUp({repr(k)}); "
        
        return command
    
    @agent_action
    def highlight_text_span(self, starting_phrase: str, ending_phrase: str,
                           button: str = "left") -> str:
        """
        Highlight text from starting phrase to ending phrase.
        
        Args:
            starting_phrase: Starting text
            ending_phrase: Ending text
            button: Mouse button to use
        """
        coords1 = self.generate_text_coords(starting_phrase, self.obs, alignment="start")
        coords2 = self.generate_text_coords(ending_phrase, self.obs, alignment="end")
        x1, y1 = coords1
        x2, y2 = coords2
        
        command = "import pyautogui; "
        command += f"pyautogui.moveTo({x1}, {y1}); "
        command += f"pyautogui.dragTo({x2}, {y2}, duration=0.5, button={repr(button)}); "
        command += "pyautogui.mouseUp(); "
        
        return command
    
    @agent_action
    def hotkey(self, keys: List[str]) -> str:
        """
        Press a hotkey combination.
        
        Args:
            keys: List of keys to press together
        """
        keys_str = ", ".join([repr(k) for k in keys])
        return f"import pyautogui; pyautogui.hotkey({keys_str})"
    
    @agent_action
    def hold_and_press(self, hold_keys: List[str], press_keys: List[str]) -> str:
        """
        Hold some keys and press others.
        
        Args:
            hold_keys: Keys to hold down
            press_keys: Keys to press
        """
        press_keys_str = "[" + ", ".join([repr(k) for k in press_keys]) + "]"
        
        command = "import pyautogui; "
        for k in hold_keys:
            command += f"pyautogui.keyDown({repr(k)}); "
        command += f"pyautogui.press({press_keys_str}); "
        for k in hold_keys:
            command += f"pyautogui.keyUp({repr(k)}); "
        
        return command
    
    @agent_action
    def open(self, app_or_filename: str) -> str:
        """
        Open an application or file.
        
        Args:
            app_or_filename: Name of app or file to open
        """
        if self.platform == "windows":
            return (f"import pyautogui; import time; "
                   f"pyautogui.keyDown('win'); pyautogui.keyUp('win'); "
                   f"time.sleep(0.5); "
                   f"pyautogui.typewrite({repr(app_or_filename)}, interval=0.01); "
                   f"time.sleep(0.5); "
                   f"pyautogui.keyDown('return'); pyautogui.keyUp('return'); "
                   f"time.sleep(1.0)")
        elif self.platform == "darwin":
            return (f"import pyautogui; import time; "
                   f"pyautogui.keyDown('command'); pyautogui.keyDown('space'); "
                   f"pyautogui.keyUp('space'); pyautogui.keyUp('command'); "
                   f"time.sleep(0.5); "
                   f"pyautogui.typewrite({repr(app_or_filename)}, interval=0.01); "
                   f"pyautogui.keyDown('return'); pyautogui.keyUp('return'); "
                   f"time.sleep(1.0)")
        else:  # linux
            return (f"import pyautogui; import time; "
                   f"pyautogui.keyDown('win'); pyautogui.keyUp('win'); "
                   f"time.sleep(0.5); "
                   f"pyautogui.typewrite({repr(app_or_filename)}, interval=0.01); "
                   f"time.sleep(0.5); "
                   f"pyautogui.keyDown('return'); pyautogui.keyUp('return'); "
                   f"time.sleep(1.0)")
    
    @agent_action
    def switch_applications(self, app_code: str) -> str:
        """
        Switch to an already open application.
        
        Args:
            app_code: Application name/identifier
        """
        return self.open(app_code)  # Same as open for now
    
    @agent_action
    def save_to_knowledge(self, text: List[str]) -> str:
        """
        Save text to knowledge bank for later use.
        
        Args:
            text: List of text strings to save
        """
        self.notes.extend(text)
        return "WAIT"
    
    @agent_action
    def wait(self, time_sec: float) -> str:
        """
        Wait for specified time.
        
        Args:
            time_sec: Seconds to wait
        """
        return f"import time; time.sleep({time_sec})"
    
    @agent_action
    def done(self) -> str:
        """Mark task as completed successfully."""
        return "DONE"
    
    @agent_action
    def fail(self) -> str:
        """Mark task as failed."""
        return "FAIL"
    
    @agent_action
    def call_code_agent(self, task: Optional[str] = None) -> str:
        """
        Call code agent for complex tasks.
        
        Args:
            task: Specific subtask (None for full task)
        """
        # This will be implemented when we create the code agent
        logger.info("Code agent called (not yet implemented)")
        return f"import time; time.sleep(2.0)"


__all__ = ['ACI', 'OSWorldACI', 'agent_action']
