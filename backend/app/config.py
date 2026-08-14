import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "AstraVerify"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Storage settings
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    
    # OCR settings
    TESSERACT_CMD: str = os.getenv(
        "TESSERACT_CMD",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe" if os.name == "nt" else "tesseract"
    )
    
    # DigiLocker OAuth Config (Real Integration)
    DIGILOCKER_CLIENT_ID: str = os.getenv("DIGILOCKER_CLIENT_ID", "")
    DIGILOCKER_CLIENT_SECRET: str = os.getenv("DIGILOCKER_CLIENT_SECRET", "")
    DIGILOCKER_REDIRECT_URI: str = os.getenv("DIGILOCKER_REDIRECT_URI", "http://localhost:8000/api/v1/digilocker/callback")
    DIGILOCKER_AUTH_URL: str = "https://api.digitallocker.gov.in/public/oauth2/1/authorize"
    DIGILOCKER_TOKEN_URL: str = "https://api.digitallocker.gov.in/public/oauth2/1/token"
    DIGILOCKER_ISSUED_DOCS_URL: str = "https://api.digitallocker.gov.in/public/oauth2/1/file/issued"
    
    # Blockchain settings (Hardhat Local / Polygon Mumbai)
    POLYGON_RPC_URL: str = os.getenv("POLYGON_RPC_URL", "http://127.0.0.1:8545")
    CONTRACT_ADDRESS: str = os.getenv("CONTRACT_ADDRESS", "")
    PRIVATE_KEY: str = os.getenv("PRIVATE_KEY", "")
    
    # Cryptographic Signing & Attestation
    SECRET_KEY: str = os.getenv("SECRET_KEY", "astraverify-super-secret-attestation-key-2026")
    ISSUER_DID: str = "did:web:astraverify.in"
    
    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()

# Ensure uploads directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
