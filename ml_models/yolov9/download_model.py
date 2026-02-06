
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # Use CPU for download

print("[INFO] Downloading YOLOv9 model...")

try:
    from ultralytics import YOLO

    # Download YOLOv9 compact model (good balance of speed/accuracy)
    # Options: yolov9t, yolov9s, yolov9m, yolov9c, yolov9e
    model = YOLO("yolov9c.pt")

    # Save to current directory
    import shutil
    if os.path.exists("yolov9c.pt"):
        shutil.move("yolov9c.pt", "model.pt")

    print("[OK] YOLOv9 model downloaded successfully")

except Exception as e:
    print(f"[ERROR] YOLOv9 download failed: {e}")
    print("[INFO] Trying YOLOv8 as fallback...")

    try:
        from ultralytics import YOLO
        model = YOLO("yolov8m.pt")

        import shutil
        if os.path.exists("yolov8m.pt"):
            shutil.move("yolov8m.pt", "model.pt")

        print("[OK] YOLOv8 model downloaded as fallback")

    except Exception as e2:
        print(f"[ERROR] Fallback download also failed: {e2}")
