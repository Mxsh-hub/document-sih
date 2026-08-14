import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_full_api_flow():
    print("Starting AstraVerify Backend API Integration Tests...")
    
    # 1. Health check endpoint
    resp = client.get("/health")
    assert resp.status_code == 200
    print("  [OK] GET /health passed:", resp.json())
    
    # 2. Upload sample PDF
    sample_pdf_path = Path(__file__).parent / "sample_test_cert.pdf"
    # Create a small dummy PDF file for testing
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), "B.Tech Degree Certificate\nName: John Doe\nCGPA: 8.95\nRoll No: CS2024101\nYear: 2024\nUniversity: Indian Institute of Technology", fontsize=14)
    doc.save(sample_pdf_path)
    doc.close()
    
    with open(sample_pdf_path, "rb") as f:
        upload_resp = client.post("/api/v1/upload", files={"file": ("sample_test_cert.pdf", f, "application/pdf")}, data={"source_type": "pdf_upload"})
    
    assert upload_resp.status_code == 200
    upload_data = upload_resp.json()
    file_id = upload_data["file_id"]
    print(f"  [OK] POST /api/v1/upload passed (File ID: {file_id})")
    
    # 3. AI Swarm Forensics Analysis
    verify_resp = client.post(f"/api/v1/verify/forensics?file_id={file_id}")
    assert verify_resp.status_code == 200
    swarm_data = verify_resp.json()
    verdict = swarm_data["swarm_result"]["verdict"]
    tier = swarm_data["swarm_result"]["tier"]
    print(f"  [OK] POST /api/v1/verify/forensics passed (Verdict: {verdict}, Tier: {tier})")
    
    # 4. Attestation VC generation
    attest_resp = client.post("/api/v1/verify/attest", json={
        "file_id": file_id,
        "holder_did": "did:example:holder123",
        "holder_name": "John Doe"
    })
    assert attest_resp.status_code == 200
    vc = attest_resp.json()
    print(f"  [OK] POST /api/v1/verify/attest passed (VC ID: {vc['id']})")
    
    # 5. DigiLocker Import (Gold Tier)
    dl_resp = client.post("/api/v1/digilocker/import", json={
        "access_token": "mock_dl_token_12345",
        "holder_did": "did:example:holder123",
        "aadhaar_last_4": "9999"
    })
    assert dl_resp.status_code == 200
    print(f"  [OK] POST /api/v1/digilocker/import passed (Imported {dl_resp.json()['documents_imported']} Gold VCs)")
    
    # 6. Issuer Direct Issuance (Gold Tier)
    issuer_resp = client.post("/api/v1/issuer/issue", json={
        "holder_did": "did:example:holder123",
        "holder_name": "John Doe",
        "document_type": "degree",
        "degree_name": "Bachelor of Technology",
        "cgpa": 8.95,
        "year_of_passing": 2024,
        "roll_number": "CS2024101",
        "university": "IIT"
    })
    assert issuer_resp.status_code == 200
    print(f"  [OK] POST /api/v1/issuer/issue passed (Issuer Anchor: {issuer_resp.json()['blockchain_anchor'][:16]}...)")
    
    # 7. Verifier Request & ZK Proof Validation
    vreq_resp = client.post("/api/v1/verifier/create-request", json={
        "verifier_did": "did:org:employer_corp",
        "purpose": "Employment Background Check",
        "criteria": [
            {"field": "cgpa", "operator": ">=", "value": 7.5},
            {"field": "degree", "operator": "in", "value": ["B.Tech", "B.E."]}
        ]
    })
    assert vreq_resp.status_code == 200
    vreq_id = vreq_resp.json()["verification_request_id"]
    print(f"  [OK] POST /api/v1/verifier/create-request passed (Req ID: {vreq_id})")
    
    zk_val_resp = client.post("/api/v1/verifier/validate-zk", json={
        "verification_request_id": vreq_id,
        "proof": "eyJwaSI6WzEsMiwzXSwiYSI6WzQsNV19",
        "public_signals": ["1", "1"]
    })
    assert zk_val_resp.status_code == 200
    val_res = zk_val_resp.json()
    print(f"  [OK] POST /api/v1/verifier/validate-zk passed (Status: {val_res['status']}, Polygon Tx Hash: {val_res['blockchain_tx_hash'][:16]}...)")
    
    # Clean up test file
    if sample_pdf_path.exists():
        sample_pdf_path.unlink()
        
    print("\nALL 7 BACKEND ENDPOINT INTEGRATION TESTS PASSED PERFECTLY!")
    return True

if __name__ == "__main__":
    test_full_api_flow()
