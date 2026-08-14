from pathlib import Path
from typing import Dict, Any, Optional
from app.services.forensics import run_forensics_analysis
from app.services.risk import run_risk_analysis
from app.services.deepfake import run_deepfake_analysis
from app.models.schemas import OrchestratorResult, ForensicsReport, RiskReport, DeepfakeReport

def run_ai_swarm(file_path: Path, source_type: str = "pdf_upload", client_metadata: Optional[Dict[str, Any]] = None) -> OrchestratorResult:
    if client_metadata is None:
        client_metadata = {}
        
    # 1. Forensics Agent (Runs ONLY on PDF, rejected for Camera photos)
    forensics_dict = run_forensics_analysis(file_path)
    
    # 2. Risk Agent (Runs on both PDF and Camera)
    risk_dict = run_risk_analysis(client_metadata)
    
    # 3. Deepfake Agent (Runs on both PDF and Camera)
    deepfake_dict = run_deepfake_analysis(file_path)
    
    forensics_report = ForensicsReport(**forensics_dict)
    risk_report = RiskReport(**risk_dict)
    deepfake_report = DeepfakeReport(**deepfake_dict)
    
    # Decision logic based on document tier & agent scores
    if source_type == "camera_upload" or forensics_dict.get("skipped", False):
        # Camera Upload -> Bronze tier
        tier = "Bronze"
        if risk_report.overall_score >= 0.6 and deepfake_report.overall_score >= 0.6:
            verdict = "PASS"
            confidence = round((risk_report.overall_score + deepfake_report.overall_score) / 2.0, 2)
            reasoning = "Camera photo passed risk & deepfake checks. Assigned Bronze Tier (OCR Record, Not ZK Ready)."
        else:
            verdict = "FAIL"
            confidence = 0.40
            reasoning = "Camera photo failed risk or deepfake authenticity threshold."
    else:
        # PDF Upload -> Potential Silver tier
        f_score = forensics_report.overall_score
        r_score = risk_report.overall_score
        d_score = deepfake_report.overall_score
        
        if f_score >= 0.80 and r_score >= 0.70 and d_score >= 0.70:
            verdict = "PASS"
            tier = "Silver"
            confidence = round((f_score * 0.5) + (r_score * 0.25) + (d_score * 0.25), 2)
            reasoning = "Document passed multi-agent AI forensics swarm with high confidence. Eligible for AstraVerify Attestation (Silver Tier, ZK Ready)."
        elif f_score < 0.50 or r_score < 0.30 or d_score < 0.40:
            verdict = "FAIL"
            tier = "Bronze"
            confidence = round((f_score + r_score + d_score) / 3.0, 2)
            reasoning = "Document failed critical AI forensics checks (inconsistent fonts, altered metadata, or risk anomalies)."
        else:
            verdict = "MANUAL_REVIEW"
            tier = "Silver"
            confidence = round((f_score + r_score + d_score) / 3.0, 2)
            reasoning = "Document shows minor anomalies requiring human reviewer verification."

    return OrchestratorResult(
        verdict=verdict,
        confidence=confidence,
        forensics=forensics_report,
        risk=risk_report,
        deepfake=deepfake_report,
        reasoning=reasoning,
        tier=tier
    )
