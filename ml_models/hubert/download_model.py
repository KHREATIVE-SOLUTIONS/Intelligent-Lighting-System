
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # Use CPU for download

print("[INFO] Downloading HuBERT model for emotion recognition...")

try:
    from transformers import Wav2Vec2FeatureExtractor, HubertForSequenceClassification

    # Using a fine-tuned HuBERT model for emotion recognition
    model_name = "superb/hubert-large-superb-er"

    print(f"[INFO] Downloading {model_name}...")

    # Download feature extractor
    feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(model_name)
    feature_extractor.save_pretrained(".")

    # Download model
    model = HubertForSequenceClassification.from_pretrained(model_name)
    model.save_pretrained(".")

    print("[OK] HuBERT model downloaded successfully")

except Exception as e:
    print(f"[ERROR] HuBERT download failed: {e}")
    print("[INFO] Trying alternative model...")

    try:
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        # Alternative: wav2vec2 for emotion
        model_name = "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"

        print(f"[INFO] Downloading {model_name}...")

        feature_extractor = AutoFeatureExtractor.from_pretrained(model_name)
        feature_extractor.save_pretrained(".")

        model = AutoModelForAudioClassification.from_pretrained(model_name)
        model.save_pretrained(".")

        print("[OK] Alternative emotion model downloaded successfully")

    except Exception as e2:
        print(f"[ERROR] Alternative download also failed: {e2}")
