"""
Application Configuration
=========================

Centralized configuration management using Pydantic settings.
"""

import os
import secrets
import warnings
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator

SECRET_KEY_FILENAME = "secret_key"

# Used when nothing sets DATABASE_URL. A venue box started with start.py has no
# Postgres server, so the old Postgres default booted with no database: the
# rig could not be patched and the operator login could not be set. A file
# beside the backend works on any machine; Docker Compose sets Postgres.
DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "lighting.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"

INSECURE_SECRET_KEYS = {
    "",
    "your-secret-key-change-in-production",
    "dev-secret-key-change-in-production-12345",
}


def resolve_data_dir(database_url: str) -> Path:
    """Return the directory the appliance keeps its state in (holds the database)."""
    if database_url.startswith("sqlite"):
        db_path = database_url.split("///", 1)[-1]
        if db_path and db_path != ":memory:":
            return Path(db_path).resolve().parent
    return Path(__file__).resolve().parents[2]


def load_or_create_secret_key(data_dir: Path) -> str:
    """Read the persisted signing secret, generating and storing one on first run.

    Tokens are signed with this key, so a key that changed per boot would log the
    operator out on every restart. Deleting the file is the "log everyone out"
    control.

    Mode 0o600 is only enforced on POSIX; on Windows os.chmod toggles the
    read-only bit alone and the file inherits the directory's ACL.
    """
    path = data_dir / SECRET_KEY_FILENAME

    try:
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except (OSError, ValueError):
        pass

    secret = secrets.token_urlsafe(48)
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            # Another process won the race; its key is authoritative.
            try:
                existing = path.read_text(encoding="utf-8").strip()
            except ValueError:
                existing = ""
            if existing:
                return existing
            fd = os.open(path, os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(secret)
        os.chmod(path, 0o600)
    except OSError as exc:
        warnings.warn(
            f"SECURITY WARNING: could not persist SECRET_KEY to {path} ({exc}). "
            "A temporary key is in use and every restart will sign the operator "
            "out. Set SECRET_KEY in the environment.",
            stacklevel=2,
        )

    return secret


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "Intelligent Lighting System"
    DEBUG: bool = False
    SECRET_KEY: str = Field(default="")

    # When False, the operator-auth middleware is bypassed entirely (dev only).
    # Defaults True so production stays gated; set AUTH_ENABLED=false to disable.
    AUTH_ENABLED: bool = True

    # Database
    DATABASE_URL: str = Field(default=DEFAULT_DATABASE_URL)

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
    AUDIO_CAPTURE_AUTO_START: bool = False

    # ML Models
    BEATNET_MODEL_PATH: str = "ml_models/beatnet/model.pt"
    HUBERT_MODEL_PATH: str = "ml_models/hubert/model.pt"
    YOLO_MODEL_PATH: str = "ml_models/yolov9/model.pt"

    # New ML Model Stack (replaces HuBERT with MERT)
    MERT_MODEL_PATH: str = "data/models/mert_v1_95m"
    EMOTION_HEAD_PATH: str = "data/models/mert_v1_95m/emotion_head.onnx"

    # Trained club genre/mood tagger (EfficientAT mn10_as, MIT). Off until it
    # has been checked against real nights; fetch the weights with
    # scripts/download_genre_model.py. It only leans palette and movement.
    GENRE_MODEL_ENABLED: bool = False
    GENRE_MODEL_PATH: str = "data/models/efficientat/mn10_as_mAP_471.pt"
    # "cpu" is enough (about 60 ms per 10 s window); "cuda" if the box has one.
    GENRE_MODEL_DEVICE: str = "cpu"

    # DMX/ArtNet
    ARTNET_IP: str = "255.255.255.255"
    ARTNET_PORT: int = 6454
    DMX_UNIVERSE: int = 0
    DMX_FPS: int = 40
    # What the nodes are left showing when output stops cleanly (shutdown,
    # disconnect, reconfigure). False holds the last look, per the roadmap's
    # "never black the room as a side effect". True sends zeros to every
    # universe so nothing - a running strobe included - stays latched on.
    DMX_BLACKOUT_ON_STOP: bool = False
    # Whether the built-in demo rig (used when nothing is patched yet) is sent
    # to the network. Off: on a fresh install the venue's own fixtures, hazers
    # and effects included, would receive a show written for a different patch.
    # Turn on to watch the demo in previs software.
    DEMO_RIG_DMX_OUTPUT: bool = False

    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30

    @property
    def data_dir(self) -> Path:
        """Directory holding the database, logs and the persisted signing secret."""
        return resolve_data_dir(self.DATABASE_URL)

    @property
    def secret_key_path(self) -> Path:
        return self.data_dir / SECRET_KEY_FILENAME

    @model_validator(mode='after')
    def validate_secret_key(self) -> 'Settings':
        if self.SECRET_KEY in INSECURE_SECRET_KEYS:
            self.SECRET_KEY = load_or_create_secret_key(
                resolve_data_dir(self.DATABASE_URL)
            )
        return self

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
