
import os
import yaml
import torch
from transformers import AutoModelForCausalLM, AutoProcessor, TrainingArguments, Trainer
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from dataset.formatting import DesktopDataset # Local import

def train():
    # Load Config
    with open("configs/lora_config.yaml", "r") as f:
        config = yaml.safe_load(f)

    print(f"Loading Model: {config['model_id']}")
    
    # 1. Load Processor
    processor = AutoProcessor.from_pretrained(config['model_id'], trust_remote_code=True)

    # 2. Load Model (Quantized load recommended for larger models, but 450M fits in fp16)
    model = AutoModelForCausalLM.from_pretrained(
        config['model_id'], 
        torch_dtype=torch.float16, 
        trust_remote_code=True,
        device_map="auto"
    )

    # 3. Apply LoRA
    peft_config = LoraConfig(
        r=config['lora_r'],
        lora_alpha=config['lora_alpha'],
        lora_dropout=config['lora_dropout'],
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=config['target_modules']
    )
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    # 4. Dummy Dataset (Replace with actual data loading logic)
    # dataset = DesktopDataset("path/to/train.json", processor, "path/to/images")
    # For now, we mock it to prevent import errors in this skeleton
    train_dataset = [] 

    # 5. Training Arguments
    training_args = TrainingArguments(
        output_dir="lfm-finetuned",
        per_device_train_batch_size=config['batch_size'],
        gradient_accumulation_steps=config['gradient_accumulation_steps'],
        learning_rate=float(config['learning_rate']),
        logging_steps=config['logging_steps'],
        num_train_epochs=config['num_train_epochs'],
        save_strategy=config['save_strategy'],
        fp16=config['fp16'],
        optim=config['optim'],
        report_to="none"
    )

    # 6. Trainer (Need custom data collator for VLM typically)
    # trainer = Trainer(
    #     model=model,
    #     args=training_args,
    #     train_dataset=train_dataset,
    #     data_collator=lambda x: x # Placeholder
    # )
    
    print("Trainer ready. (Uncomment dataset loading to run real training)")
    # trainer.train()
    
    # 7. Save Adapter
    # model.save_pretrained("lfm-finetuned/adapter")

if __name__ == "__main__":
    train()
