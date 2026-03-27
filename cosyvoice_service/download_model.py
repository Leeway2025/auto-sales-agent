"""Download CosyVoice2-0.5B model from ModelScope.

Used by entrypoint.sh when MODEL_DOWNLOAD=1.
"""
import os
from modelscope import snapshot_download

model_dir = os.getenv("COSYVOICE_MODEL_DIR", "/workspace/models/CosyVoice2-0.5B")
os.makedirs(os.path.dirname(model_dir), exist_ok=True)

print(f"Downloading CosyVoice2-0.5B to {model_dir} ...")
snapshot_download("iic/CosyVoice2-0.5B", local_dir=model_dir)
print("Download complete.")
