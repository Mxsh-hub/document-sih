import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

def test_imports():
    print("Testing backend module imports...")
    try:
        from app.config import settings
        print("  [OK] app.config.settings loaded")
        
        from app.models import schemas
        print("  [OK] app.models.schemas loaded")
        
        from app.services import storage, ocr, forensics, risk, deepfake, orchestrator, attestation
        print("  [OK] app.services modules loaded")
        
        from app.routers import upload, digilocker, issuer, verify, verifier
        print("  [OK] app.routers modules loaded")
        
        from app.main import app
        print("  [OK] app.main FastAPI app initialized cleanly")
        
        print("\nAll backend modules imported successfully!")
        return True
    except Exception as e:
        print(f"\n❌ Import error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
