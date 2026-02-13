
import json
from PIL import Image
import torch

def format_instruction(task_description, som_tags=None):
    """
    Formats the input instruction for LFM2-VL based on UI-TARS schema.
    If SoM tags are present, prompts the model to select the correct ID.
    """
    base_prompt = f"User: {task_description}\n"
    if som_tags:
        base_prompt += "Visible Elements:\n" + "\n".join([f"- ID {tag['id']}: {tag['type']}" for tag in som_tags])
        base_prompt += "\nSelect the ID of the element to interact with.\n"
    
    base_prompt += "Assistant:"
    return base_prompt

def load_and_process_image(image_path, processor):
    """
    Loads an image and processes it using the LFM2-VL processor.
    """
    try:
        image = Image.open(image_path).convert("RGB")
        return processor(images=image, return_tensors="pt")
    except Exception as e:
        print(f"Error processing image {image_path}: {e}")
        return None

class DesktopDataset(torch.utils.data.Dataset):
    def __init__(self, data_json, processor, img_dir):
        self.data = json.load(open(data_json))
        self.processor = processor
        self.img_dir = img_dir

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        item = self.data[idx]
        task = item['instruction']
        target_action = item['action'] # e.g., "CLICK(5)"
        img_path = f"{self.img_dir}/{item['image_id']}.png"

        # instruction format
        instruction = format_instruction(task)
        
        # Process inputs
        # Note: In a real trainer, you'd handle tokenization here or in collator
        return {
            "image_path": img_path,
            "instruction": instruction,
            "target": target_action
        }
