"""
Application Configuration
=========================

Centralized configuration management using Pydantic settings.
"""

import secrets
import warnings
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "Intelligent Lighting System"
    DEBUG: bool = False
    SECRET_KEY: str = Field(default="")

    # Database
    DATABASE_URL: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/lighting_db"
    )

    # Redis (for caching and pub/sub)
    REDIS_URL: str = Field(default="redis://localhost:6379")

    # CORS
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"]
    )

    # Audio Analysis
    AUDIO_SAMPLE_RATE: int = 44100
    AUDIO_CHUNK_SIZE: int = 2048
    AUDIO_HOP_LENGTH: int = 512

    # ML Models
    BEATNET_MODEL_PATH: str = "ml_models/beatnet/model.pt"
    HUBERT_MODEL_PATH: str = "ml_models/hubert/model.pt"
    YOLO_MODEL_PATH: str = "ml_models/yolov9/model.pt"

    # New ML Model Stack (replaces HuBERT with MERT)
    MERT_MODEL_PATH: str = "data/models/mert_v1_95m"
    EMOTION_HEAD_PATH: str = "data/models/mert_v1_95m/emotion_head.onnx"

    # DMX/ArtNet
    ARTNET_IP: str = "0.0.0.0"
    ARTNET_PORT: int = 6454
    DMX_UNIVERSE: int = 0
    DMX_FPS: int = 40

    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30

    @model_validator(mode='after')
    def validate_secret_key(self) -> 'Settings':
        insecure_defaults = {"", "your-secret-key-change-in-production",
                             "dev-secret-key-change-in-production-12345"}
        if self.SECRET_KEY in insecure_defaults:
            if self.DEBUG:
                # Generate a random key for development, but warn
                self.SECRET_KEY = secrets.token_urlsafe(32)
                warnings.warn(
                    "SECRET_KEY not set - generated random key for development. "
                    "Set SECRET_KEY in .env for production.",
                    stacklevel=2,
                )
            else:
                # In production, generate a random key and emit a strong warning
                self.SECRET_KEY = secrets.token_urlsafe(32)
                warnings.warn(
                    "SECURITY WARNING: SECRET_KEY not configured! "
                    "A random key was generated but will change on restart. "
                    "Set SECRET_KEY in your .env file for production use.",
                    stacklevel=2,
                )
        return self

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
