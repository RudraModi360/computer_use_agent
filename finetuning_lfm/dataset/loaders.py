
from datasets import load_dataset
from torch.utils.data import Dataset
from .formatting import format_instruction

class ScreenSpotDataset(Dataset):
    """
    Loader for the ScreenSpot dataset (Grounding).
    Maps: Instruction -> Bounding Box (or SoM ID)
    """
    def __init__(self, processor, split="train"):
        print("Loading ScreenSpot dataset...")
        # Assuming typical HF dataset structure for ScreenSpot
        self.dataset = load_dataset("rootsautomation/ScreenSpot", split=split) 
        self.processor = processor

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, idx):
        item = self.dataset[idx]
        image = item['image']
        instruction = item['instruction']
        bbox = item['bbox'] # [x1, y1, x2, y2]
        
        # Format for LFM:
        # User: <instruction>
        # Assistant: <bbox> (normalized to 0-1000 or SoM ID)
        
        formatted_instruction = format_instruction(instruction)
        target_text = str(bbox) # Needs normalization function to 0-1000 based on image size
        
        # Note: Actual implementation needs image processing to align bbox
        return {
            "image": image,
            "text": formatted_instruction,
            "target": target_text
        }

class Mind2WebDataset(Dataset):
    """
    Loader for Mind2Web (Action Prediction).
    Maps: Instruction + HTML/Image -> Action Sequence
    """
    def __init__(self, processor, split="train"):
        self.dataset = load_dataset("osunlp/Mind2Web", split=split)
        self.processor = processor

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, idx):
        item = self.dataset[idx]
        # Mind2Web has 'action_reprs'
        return item
