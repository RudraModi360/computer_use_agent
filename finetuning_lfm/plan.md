# Research Plan: Fine-Tuning & Quantizing LFM2-VL-450M for GUI Agents

## 1. Objective
Fine-tune **LiquidAI LFM2-VL-450M** to replicate **UI-TARS** capabilities (grounding, navigation, action execution) on edge devices, followed by quantization for optimal performance.

## 2. Theoretical Foundation (UI-TARS Adaptation)
The UI-TARS paper emphasizes three core components we must adapt to the smaller 450M model:

1.  **Perception (Element Grounding):**
    *   *UI-TARS approach:* Visual-Language alignment on GUI elements (buttons, icons).
    *   *LFM-450M adaptation:* Fine-tune strictly on **ScreenSpot** (Coordinate -> Element ID) and **Mind2Web** (Task -> Element).
    *   *Constraint:* 450M cannot reliably generate raw `[0-1000]` coordinates zero-shot. We will fine-tune it to predict **Set-of-Mark (SoM) IDs** or **Region References**.

2.  **Action Space (Unified Schema):**
    *   *Format:* `ActionType(ElementID, Optional[Text])`
    *   *Vocabulary:* `CLICK`, `TYPE`, `SCROLL`, `HOVER`.
    *   We will tokenize these actions as special tokens to minimize context length.

3.  **Data Strategy (The "Data Flywheel" Lite):**
    *   We cannot run the full iterative training loop of UI-TARS.
    *   Instead, we use a static high-quality dataset:
        -   **ScreenSpot:** For pure grounding (Where is "File"? -> "Region <box_2d>").
        -   **AndroidControl/Mind2Web:** For Action prediciton (Task "Search for shoes" -> `CLICK(SearchBox)` -> `TYPE("shoes")`).

## 3. Implementation Architecture (`finetuning_lfm/`)

The solution is modularized for maintainability and scalability.

```
finetuning_lfm/
├── configs/           # Hyperparameters (LoRA, Quantization)
├── core/             # Model wrappers and training logic
│   ├── model_loader.py   # LFM2-specific loading (handling mrope/rotary embeddings)
│   ├── tokenizer.py      # Special token handling for UI actions
│   └── trainer.py        # Custom SFTTrainer adaptation
├── dataset/          # Data processing pipeline
│   ├── formatting.py     # Convert raw datasets to VLM instruction format
│   └── screenspot.py     # Loader for ScreenSpot dataset
├── scripts/          # Execution entry points
│   ├── train.py          # Main training script
│   ├── convert_to_gguf.py # Quantization script
│   └── test_inference.py # Validation
└── README.md
```

## 4. Workflows

### Phase 1: Preparation
1.  **Model Loading:** Ensure LFM2-VL loads with `transformers` and `peft` (for LoRA). Full fine-tuning 450M is possible on consumer GPUs (12GB+ VRAM), but LoRA is safer for stability.
2.  **Dataset Formatting:** Convert UI-TARS/ScreenSpot data into `(Image, Instruction, Output)` tuples.
    *   *Input:* User Instruction + Screen Screenshot (with optional SoM overlays).
    *   *Output:* Target Action token.

### Phase 2: Fine-Tuning (SFT)
*   **Technique:** Low-Rank Adaptation (LoRA) targeting `q_proj`, `v_proj` of the attention layers.
*   **Vision Adapter:** We *unfreeze* the vision projector to align the visual encoder with GUI-specific features (sharp lines, text) which differ from natural images.
*   **Hyperparameters:**
    *   Batch Size: 4 (Small model allows larger batches).
    *   Learning Rate: 2e-4 (Standard for LoRA).
    *   Epochs: 3.

### Phase 3: Quantization (GGUF)
*   Post-training, we fuse the LoRA adapters back into the base model.
*   Use `llama.cpp`'s `convert-hf-to-gguf.py` to convert the fused model to GGUF format.
*   Use `llama-quantize` to generate `Q4_K_M` (Balanced) and `Q8_0` (High Accuracy) variants.

## 5. Success Metrics
1.  **Grounding Accuracy:** % of correct Element IDs predicted.
2.  **Action Validity:** % of generated strings that match the valid action schema.
3.  **Inference Latency:** Target < 500ms on Edge CPU (post-quantization).
