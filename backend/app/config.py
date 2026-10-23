import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    PROJECT_NAME: str = "AstraVerify"
    VERSION: str = "0.3.0"
    API_V1_STR: str = "/api/v1"

    # Storage settings
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    OBJECT_STORE_DIR: Path = BASE_DIR / "object_store"
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "local")

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://astra:astra@localhost:55432/astra",
    )

    # Authentication
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))
    REFRESH_TOKEN_DAYS: int = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))
    DOWNLOAD_SIGNING_KEY: str = os.getenv("DOWNLOAD_SIGNING_KEY", "")

    # CORS: comma-separated origins. Never use "*" with credentials.
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:5173")

    # Upload policy
    MAX_DOCUMENT_BYTES: int = 25 * 1024 * 1024
    MAX_REQUEST_BYTES: int = 26 * 1024 * 1024
    MAX_PDF_PAGES: int = int(os.getenv("MAX_PDF_PAGES", "200"))
    LOGIN_MAX_FAILURES: int = int(os.getenv("LOGIN_MAX_FAILURES", "8"))
    LOGIN_WINDOW_SECONDS: int = int(os.getenv("LOGIN_WINDOW_SECONDS", "900"))
    INFRASTRUCTURE_REQUIRED_TYPES: str = os.getenv(
        "INFRASTRUCTURE_REQUIRED_TYPES", "PHOTO,FLOOR_PLAN,CERTIFICATE"
    )
    PROCESS_DOCUMENTS_INLINE: bool = os.getenv("PROCESS_DOCUMENTS_INLINE", "true").lower() in {
        "1",
        "true",
        "yes",
    }

    # S3 / MinIO
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL", "")
    S3_ACCESS_KEY: str = os.getenv("S3_ACCESS_KEY", "")
    S3_SECRET_KEY: str = os.getenv("S3_SECRET_KEY", "")
    S3_BUCKET: str = os.getenv("S3_BUCKET", "astra-documents")
    S3_REGION: str = os.getenv("S3_REGION", "us-east-1")

    # OCR settings
    TESSERACT_CMD: str = os.getenv(
        "TESSERACT_CMD",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe" if os.name == "nt" else "tesseract",
    )

    # DigiLocker OAuth Config (legacy demo)
    DIGILOCKER_CLIENT_ID: str = os.getenv("DIGILOCKER_CLIENT_ID", "")
    DIGILOCKER_CLIENT_SECRET: str = os.getenv("DIGILOCKER_CLIENT_SECRET", "")
    DIGILOCKER_REDIRECT_URI: str = os.getenv(
        "DIGILOCKER_REDIRECT_URI",
        "http://localhost:8000/api/v1/digilocker/callback",
    )
    DIGILOCKER_AUTH_URL: str = "https://api.digitallocker.gov.in/public/oauth2/1/authorize"
    DIGILOCKER_TOKEN_URL: str = "https://api.digitallocker.gov.in/public/oauth2/1/token"
    DIGILOCKER_ISSUED_DOCS_URL: str = "https://api.digitallocker.gov.in/public/oauth2/1/file/issued"

    # Legacy blockchain settings
    POLYGON_RPC_URL: str = os.getenv("POLYGON_RPC_URL", "http://127.0.0.1:8545")
    CONTRACT_ADDRESS: str = os.getenv("CONTRACT_ADDRESS", "")
    PRIVATE_KEY: str = os.getenv("PRIVATE_KEY", "")

    # Legacy signing/attestation
    SECRET_KEY: str = os.getenv("SECRET_KEY", "astraverify-super-secret-attestation-key-2026")
    ISSUER_DID: str = "did:web:astraverify.in"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def download_signing_key(self) -> str:
        return self.DOWNLOAD_SIGNING_KEY or self.JWT_SECRET

    @property
    def infrastructure_required_types(self) -> list[str]:
        return [item.strip().upper() for item in self.INFRASTRUCTURE_REQUIRED_TYPES.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    # ZKP configuration
    CIRCUITS_DIR: Path = BASE_DIR / "circuits"
    ZKP_VKEY_PATH: Path = BASE_DIR / "circuits" / "faculty_threshold" / "verification_key.json"
    ZKP_WASM_PATH: Path = BASE_DIR / "circuits" / "faculty_threshold" / "faculty_threshold.wasm"
    ZKP_ZKEY_PATH: Path = BASE_DIR / "circuits" / "faculty_threshold" / "faculty_threshold_final.zkey"
    ZKP_LEGACY_VKEY_PATH: Path = BASE_DIR.parent / "circuits" / "verification_key.json"
    ZKP_ENABLED: bool = os.getenv("ZKP_ENABLED", "true").lower() == "true"
    ZKP_CHALLENGE_TTL_SECONDS: int = int(os.getenv("ZKP_CHALLENGE_TTL_SECONDS", "600"))
    FACULTY_THRESHOLD_SCALED: int = int(os.getenv("FACULTY_THRESHOLD_SCALED", "700"))
    SNARKJS_BIN: str = os.getenv("SNARKJS_BIN", "")
    ZKP_ALLOW_LEGACY_CIRCUIT: bool = os.getenv("ZKP_ALLOW_LEGACY_CIRCUIT", "false").lower() == "true"

    # Blockchain anchoring
    BLOCKCHAIN_ENABLED: bool = os.getenv("BLOCKCHAIN_ENABLED", "false").lower() == "true"
    BLOCKCHAIN_NETWORK: str = os.getenv("BLOCKCHAIN_NETWORK", "hardhat")
    BLOCKCHAIN_RPC_URL: str = os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545")
    BLOCKCHAIN_PRIVATE_KEY: str = os.getenv("BLOCKCHAIN_PRIVATE_KEY", "")
    ASTRA_VERIFY_ANCHOR_ADDRESS: str = os.getenv("ASTRA_VERIFY_ANCHOR_ADDRESS", "")
    FACULTY_THRESHOLD_VERIFIER_ADDRESS: str = os.getenv("FACULTY_THRESHOLD_VERIFIER_ADDRESS", "")
    BLOCKCHAIN_ARTIFACT_PATH: Path = BASE_DIR.parent / "blockchain" / "artifacts" / "contracts" / "AstraVerifyAnchorV2.sol" / "AstraVerifyAnchorV2.json"
    BLOCKCHAIN_PROOF_ANCHORING_ENABLED: bool = os.getenv("BLOCKCHAIN_PROOF_ANCHORING_ENABLED", "false").lower() == "true"


settings = Settings()

# Ensure legacy and object-store directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.OBJECT_STORE_DIR, exist_ok=True)

