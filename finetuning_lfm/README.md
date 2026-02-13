# LFM2-VL-450M Fine-Tuning & Quantization Module

This directory contains the complete modular framework for fine-tuning the **LiquidAI LFM2-VL-450M** model to adapt **UI-TARS** capabilities for edge devices.

## Directory Structure
- **`configs/`**: YAML configuration files for LoRA and training hyperparameters.
- **`core/`**: Core logic including model loading overrides and custom trainers.
- **`dataset/`**: Data processing pipelines for ScreenSpot and Mind2Web.
- **`scripts/`**: Entry points for training and quantization.

## Usage

### 1. Install Dependencies
```bash
pip install torch transformers peft datasets bitsandbytes accelerate
```

### 2. Fine-Tuning
Run the training script to fine-tune the model on UI data:
```bash
python scripts/train.py
```
*Note: Ensure you have populated the dataset paths in `dataset/loaders.py`.*

### 3. Quantization
After training, convert the model to GGUF format for optimal edge performance:
```bash
python scripts/quantize.py --model_dir lfm-finetuned/adapter --output_dir ./gguf_models --llama_cpp_path /path/to/llama.cpp
```

## Adaptation Strategy
This framework adapts the **UI-TARS** architecture by:
1.  **Vision Grounding**: Fine-tuning the visual encoder to recognize UI elements (ScreenSpot).
2.  **Edge Action Space**: Mapping complex reasoning to direct atomic actions (`CLICK`, `TYPE`) to suit the 450M parameter size.
