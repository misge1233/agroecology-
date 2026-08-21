"""Application configuration from environment variables.

The recommender engine (``backend/recommend.py``) is self-contained: it resolves
its own model / dataset / raster paths relative to the ``backend/`` folder. This
settings object only carries app-level knobs (OpenAI chat, CORS, rate limiting) plus the
absolute location of ``backend/`` so the service layer can put it on ``sys.path``.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# app/config.py -> parents[1] = backend/  (holds recommend.py, groq_agent.py,
# artifacts/, dataset/, layers/, aez_belt_lookup.csv)
BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AgroAdvisor-ET — AI-Powered Agroecology+ Advisor"
    debug: bool = False

    # Root that holds the canonical engine + ML artifacts.
    backend_root: Path = BACKEND_ROOT

    # GeoTIFF stack directory. Empty -> backend_root/layers (the docker-compose
    # mount point). For local dev point it at the repo's canonical copy, e.g.
    # LAYERS_DIR=../../geodata/layers in backend/.env (relative paths resolve
    # against backend/).
    layers_dir: str = Field(
        default="",
        validation_alias=AliasChoices("LAYERS_DIR"),
    )

    # RAG evidence index (Phase P2b). Built by rag/ingest (fetch_papers →
    # parse_and_chunk → build_index); lives at the repo root by default. Relative
    # paths resolve against backend_root, mirroring LAYERS_DIR.
    rag_index_dir: str = Field(
        default="../../rag/index/store",
        validation_alias=AliasChoices("RAG_INDEX_DIR"),
    )
    rag_chunks_path: str = Field(
        default="../../rag/corpus/chunks.jsonl",
        validation_alias=AliasChoices("RAG_CHUNKS_PATH"),
    )
    # Tier-2 guidance corpus (Phase P5a) — optional; a missing file simply
    # disables the guidance layer of /explain.
    rag_guidance_chunks_path: str = Field(
        default="../../rag/corpus/guidance/chunks.jsonl",
        validation_alias=AliasChoices("RAG_GUIDANCE_CHUNKS_PATH"),
    )

    # OpenAI chat — set OPENAI_API_KEY in backend/.env; model/URL live in openai_chat.py
    openai_api_key: str = ""
    openai_timeout_seconds: float = Field(
        default=60.0,
        validation_alias=AliasChoices("OPENAI_TIMEOUT_SECONDS"),
    )

    # CORS — comma-separated origins
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Rate limiting (chat)
    chat_rate_limit_per_minute: int = 20

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def resolved_layers_dir(self) -> Path:
        """Absolute path of the raster stack (LAYERS_DIR or backend_root/layers)."""
        if self.layers_dir:
            p = Path(self.layers_dir)
            return p if p.is_absolute() else (self.backend_root / p).resolve()
        return self.backend_root / "layers"

    @property
    def resolved_rag_index_dir(self) -> Path:
        """Absolute path of the persistent Chroma index (RAG_INDEX_DIR)."""
        p = Path(self.rag_index_dir)
        return p if p.is_absolute() else (self.backend_root / p).resolve()

    @property
    def resolved_rag_chunks_path(self) -> Path:
        """Absolute path of the corpus chunks JSONL (RAG_CHUNKS_PATH)."""
        p = Path(self.rag_chunks_path)
        return p if p.is_absolute() else (self.backend_root / p).resolve()

    @property
    def resolved_rag_guidance_chunks_path(self) -> Path:
        """Absolute path of the Tier-2 guidance chunks JSONL (optional)."""
        p = Path(self.rag_guidance_chunks_path)
        return p if p.is_absolute() else (self.backend_root / p).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
