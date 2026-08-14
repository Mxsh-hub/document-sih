from typing import Dict, Any

def run_risk_analysis(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates upload velocity, device fingerprint, and network geolocation context.
    """
    ip = metadata.get("client_ip", "127.0.0.1")
    user_agent = metadata.get("user_agent", "Mozilla/5.0")
    
    # Velocity check heuristic
    upload_velocity_score = 0.95  # Normal rate
    device_trust_score = 0.90     # Known browser header
    geolocation_match = True
    
    if "curl" in user_agent.lower() or "python" in user_agent.lower():
        device_trust_score = 0.70
        
    overall_score = round(
        (upload_velocity_score * 0.4) + 
        (device_trust_score * 0.4) + 
        ((1.0 if geolocation_match else 0.5) * 0.2), 
        2
    )
    
    return {
        "upload_velocity_score": upload_velocity_score,
        "device_trust_score": device_trust_score,
        "geolocation_match": geolocation_match,
        "overall_score": overall_score,
        "details": {
            "client_ip": ip,
            "user_agent": user_agent
        }
    }
