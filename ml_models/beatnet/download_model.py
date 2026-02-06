
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # Use CPU for download
try:
    from BeatNet.BeatNet import BeatNet
    # Initialize to trigger model download
    estimator = BeatNet(1, mode='offline', inference_model='DBN', plot=[], thread=False)
    print("[OK] BeatNet model downloaded successfully")
except Exception as e:
    print(f"[INFO] BeatNet setup: {e}")
    print("[INFO] Model will be downloaded on first use")
