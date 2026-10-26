from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Literal, Union, Dict, Any
from datetime import datetime

# Upload Models
class UploadResponse(BaseModel):
    file_id: str
    filename: str
    content_type: str
    size_bytes: int
    status: Literal["received", "processing", "verified", "failed"]
    message: str
    source_type: Optional[Literal["pdf_upload", "camera_upload"]] = "pdf_upload"

# DigiLocker Models
class DigiLockerAuthRequest(BaseModel):
    aadhaar_last_4: str = Field(..., min_length=4, max_length=4)
    otp: str = Field(..., min_length=6, max_length=6)

class DigiLockerOAuthToken(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    digilockerid: Optional[str] = None
    name: Optional[str] = None
    dob: Optional[str] = None
    gender: Optional[str] = None

class DigiLockerImportResponse(BaseModel):
    status: str
    documents_imported: int
    credentials: List[dict]

# W3C Verifiable Credentials Models
class W3CProof(BaseModel):
    # No default: callers must state what the proof actually is. The legacy demo
    # endpoints use AstraDemoHmacIntegrity / AstraSimulatedProof, the attestation
    # helper uses AstraEd25519Signature. None of them is a W3C Data Integrity proof.
    type: str
    created: str
    proofPurpose: str = "assertionMethod"
    verificationMethod: str
    proofValue: str

class W3CCredentialSubject(BaseModel):
    id: str
    name: str
    document_type: str
    degree: Optional[str] = None
    cgpa: Optional[float] = None
    year: Optional[int] = None
    roll_number: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    years_of_experience: Optional[float] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None

class W3CVerifiableCredential(BaseModel):
    context: List[str] = Field(default=["https://www.w3.org/2018/credentials/v1"], alias="@context")
    id: str
    type: List[str]
    issuer: str
    issuanceDate: str
    credentialSubject: W3CCredentialSubject
    proof: W3CProof
    
    model_config = ConfigDict(populate_by_name=True)

# Issuer Models
class IssueCredentialRequest(BaseModel):
    holder_did: str
    holder_name: str
    document_type: Literal["degree", "experience", "identity", "professional"]
    degree_name: Optional[str] = None
    cgpa: Optional[float] = Field(None, ge=0, le=10)
    year_of_passing: Optional[int] = None
    roll_number: Optional[str] = None
    university: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    years_of_experience: Optional[float] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None

class IssueCredentialResponse(BaseModel):
    status: str
    credential_id: str
    vc: W3CVerifiableCredential
    blockchain_anchor: Optional[str] = None

# AI Multi-Agent Swarm Models
class ForensicsReport(BaseModel):
    font_consistency_score: float
    metadata_clean: bool
    seal_detected: bool
    tamper_probability: float
    overall_score: float
    details: Optional[Dict[str, Any]] = None

class RiskReport(BaseModel):
    upload_velocity_score: float
    device_trust_score: float
    geolocation_match: bool
    overall_score: float
    details: Optional[Dict[str, Any]] = None

class DeepfakeReport(BaseModel):
    ai_generated_probability: float
    synthetic_signature_detected: bool
    overall_score: float
    details: Optional[Dict[str, Any]] = None

class OrchestratorResult(BaseModel):
    verdict: Literal["PASS", "FAIL", "MANUAL_REVIEW"]
    confidence: float
    forensics: Optional[ForensicsReport] = None
    risk: Optional[RiskReport] = None
    deepfake: Optional[DeepfakeReport] = None
    reasoning: str
    tier: Optional[Literal["Gold", "Silver", "Bronze"]] = None

# Document Attestation Request
class AttestRequest(BaseModel):
    file_id: str
    holder_did: str
    holder_name: str

# Verifier & ZK Models
class VerificationCriterion(BaseModel):
    field: str
    operator: Literal["==", ">=", "<=", ">", "<", "in"]
    value: Union[str, float, int, List[str]]

class VerificationRequest(BaseModel):
    verifier_did: str
    purpose: str
    criteria: List[VerificationCriterion]

class VerificationRequestResponse(BaseModel):
    verification_request_id: str
    verifier_did: str
    purpose: str
    criteria: List[VerificationCriterion]
    created_at: str

class ZKProofSubmission(BaseModel):
    verification_request_id: str
    proof: str  # base64 encoded proof or JSON string
    public_signals: List[str]

class VerificationResult(BaseModel):
    verification_id: str
    status: Literal["APPROVED", "REJECTED", "PENDING"]
    criterion_results: List[Dict[str, Any]]
    overall_confidence: float
    blockchain_tx_hash: Optional[str] = None
