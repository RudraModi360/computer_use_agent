
import os
import subprocess
import argparse

def quantize_model(model_dir, output_dir, llama_cpp_path):
    """
    Quantizes a Hugging Face model to GGUF format using llama.cpp tools.
    1. Convert HF -> GGUF (f16)
    2. Quantize GGUF -> Q4_K_M / Q8_0
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Define paths
    convert_script = os.path.join(llama_cpp_path, "convert-hf-to-gguf.py")
    quantize_exe = os.path.join(llama_cpp_path, "build", "bin", "llama-quantize") # Adjust based on actual path
    
    # Step 1: Convert to GGUF (F16)
    f16_output = os.path.join(output_dir, "lfm2-vl-450m-f16.gguf")
    print(f"--- Step 1: Converting to GGUF (F16) ---")
    cmd_convert = [
        "python", convert_script,
        model_dir,
        "--outfile", f16_output,
        "--outtype", "f16"
    ]
    
    # Note: user might need to install 'sentencepiece' and 'gguf' pip packages
    subprocess.run(cmd_convert, check=True)
    
    # Step 2: Quantize to Q4_K_M
    q4_output = os.path.join(output_dir, "lfm2-vl-450m-q4_k_m.gguf")
    print(f"--- Step 2: Quantizing to Q4_K_M ---")
    cmd_quantize = [
        quantize_exe,
        f16_output,
        q4_output,
        "Q4_K_M"
    ]
    subprocess.run(cmd_quantize, check=True)
    
    print(f"Quantization complete. Model saved to {q4_output}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_dir", type=str, required=True, help="Path to fused HF model")
    parser.add_argument("--output_dir", type=str, required=True, help="Output directory for GGUF")
    parser.add_argument("--llama_cpp_path", type=str, default="llama.cpp", help="Path to llama.cpp root")
    args = parser.parse_args()
    
    quantize_model(args.model_dir, args.output_dir, args.llama_cpp_path)
