import React, { useState } from 'react';
import { FileBadge, Loader2, Link as LinkIcon, Building2, CheckCircle2 } from 'lucide-react';
import { ethers } from 'ethers';

export default function IssuerPortal() {
  const [formData, setFormData] = useState({
    holder_did: 'did:web:astraverify.in:user:123',
    holder_name: 'Aruna',
    document_type: 'degree',
    degree_name: 'B.Tech Computer Science',
    cgpa: 8.5,
    year_of_passing: 2026,
    university: 'Astra University',
    company: '',
    role: '',
    years_of_experience: 0,
    id_type: '',
    id_number: ''
  });

  const [isIssuing, setIsIssuing] = useState(false);
  const [issueResult, setIssueResult] = useState(null);

  const contractAddress = import.meta.env.VITE_CONTRACT_ADDRESS || "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512";
  const contractABI = [
    "function anchorDocument(bytes32 _docHash, string calldata _tier) external",
    "event DocumentAnchored(bytes32 indexed docHash, address indexed issuer, string tier, uint256 timestamp)"
  ];

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleIssue = async (e) => {
    e.preventDefault();
    setIsIssuing(true);
    setIssueResult(null);

    try {
      // 1. Issue via Backend (Creates VC, signs it, computes hash)
      const apiRes = await fetch("http://localhost:8000/api/v1/issuer/issue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData)
      });
      
      if (!apiRes.ok) {
        throw new Error("Failed to issue credential from backend.");
      }
      
      const issueData = await apiRes.json();
      const docHash = issueData.blockchain_anchor;

      let txHash = "Pending...";
      
      // 2. Anchor on Blockchain (Ethers.js)
      try {
        if (!window.ethereum) throw new Error("Please install MetaMask to issue credentials on the live network.");
        await window.ethereum.request({ method: 'eth_requestAccounts' });
        const provider = new ethers.BrowserProvider(window.ethereum);
        const signer = await provider.getSigner();
        const contract = new ethers.Contract(contractAddress, contractABI, signer);
        
        const tx = await contract.anchorDocument(docHash, "Gold", {
            maxPriorityFeePerGas: ethers.parseUnits('40', 'gwei'),
            maxFeePerGas: ethers.parseUnits('50', 'gwei')
        });
        await tx.wait();
        txHash = tx.hash;
      } catch (blockchainErr) {
        console.error("Blockchain anchoring failed:", blockchainErr);
        throw new Error("Blockchain anchoring failed: " + blockchainErr.message);
      }

      setIssueResult({
        status: "SUCCESS",
        credential_id: issueData.credential_id,
        blockchain_anchor: docHash,
        txHash: txHash
      });

    } catch (err) {
      console.error(err);
      setIssueResult({
        status: "ERROR",
        message: err.message
      });
    } finally {
      setIsIssuing(false);
    }
  };

  return (
    <div className="py-8 space-y-6">
      <div className="flex items-center gap-3 border-b-4 border-border pb-4">
        <Building2 size={36} className="text-primary" />
        <h1 className="text-4xl font-black uppercase">Issuer Portal</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        
        {/* Issuance Form */}
        <div className="neo-box p-6 bg-card space-y-6">
          <div className="space-y-1">
            <h2 className="text-2xl font-bold uppercase tracking-tight">Mint Credential</h2>
            <p className="font-serif text-muted-foreground">Issue a mathematically verified Gold Tier document to a user.</p>
          </div>

          <form onSubmit={handleIssue} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-bold uppercase">Holder DID</label>
                <input required type="text" name="holder_did" value={formData.holder_did} onChange={handleInputChange} className="neo-input w-full" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-bold uppercase">Holder Name</label>
                <input required type="text" name="holder_name" value={formData.holder_name} onChange={handleInputChange} className="neo-input w-full" />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-bold uppercase">Document Type</label>
              <select name="document_type" value={formData.document_type} onChange={handleInputChange} className="neo-input w-full bg-white">
                <option value="degree">Academic Degree</option>
                <option value="experience">Experience Letter</option>
                <option value="identity">Identity Card</option>
                <option value="professional">Professional Certificate</option>
              </select>
            </div>

            {formData.document_type === 'degree' && (
              <>
                <div className="space-y-2">
                  <label className="text-sm font-bold uppercase">University Name</label>
                  <input type="text" name="university" value={formData.university} onChange={handleInputChange} className="neo-input w-full" />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-sm font-bold uppercase">Degree Name</label>
                    <input type="text" name="degree_name" value={formData.degree_name} onChange={handleInputChange} className="neo-input w-full" />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-bold uppercase">CGPA (0-10)</label>
                    <input type="number" step="0.1" name="cgpa" value={formData.cgpa} onChange={handleInputChange} className="neo-input w-full" />
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-bold uppercase">Year of Passing</label>
                  <input type="number" name="year_of_passing" value={formData.year_of_passing} onChange={handleInputChange} className="neo-input w-full" />
                </div>
              </>
            )}

            {formData.document_type === 'experience' && (
              <>
                <div className="space-y-2">
                  <label className="text-sm font-bold uppercase">Company Name</label>
                  <input type="text" name="company" value={formData.company} onChange={handleInputChange} className="neo-input w-full" />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-sm font-bold uppercase">Role</label>
                    <input type="text" name="role" value={formData.role} onChange={handleInputChange} className="neo-input w-full" />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-bold uppercase">Years of Exp</label>
                    <input type="number" step="0.1" name="years_of_experience" value={formData.years_of_experience} onChange={handleInputChange} className="neo-input w-full" />
                  </div>
                </div>
              </>
            )}

            <button type="submit" disabled={isIssuing} className="neo-button w-full flex justify-center items-center py-3 bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              {isIssuing ? <><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Issuing & Anchoring...</> : <><FileBadge className="mr-2 h-5 w-5" /> Issue Credential</>}
            </button>
          </form>
        </div>

        {/* Results Panel */}
        <div className="space-y-6">
          <div className="neo-box p-6 bg-sidebar text-sidebar-foreground border-sidebar-border h-full">
            <h2 className="text-2xl font-bold uppercase mb-4 text-sidebar-primary">Issuance Status</h2>
            
            {!issueResult && !isIssuing && (
              <div className="flex flex-col items-center justify-center h-48 opacity-70">
                <FileBadge size={48} className="mb-4" />
                <p className="font-mono text-sm">Ready to mint credentials.</p>
              </div>
            )}

            {isIssuing && (
              <div className="flex flex-col items-center justify-center h-48 space-y-4">
                <Loader2 size={48} className="animate-spin text-sidebar-primary" />
                <p className="font-mono text-sm animate-pulse">Computing Cryptographic Signatures...</p>
              </div>
            )}

            {issueResult && issueResult.status === "SUCCESS" && (
              <div className="space-y-4">
                <div className="bg-green-950/50 p-4 border-2 border-green-500 rounded-none flex items-start gap-3">
                  <CheckCircle2 className="text-green-500 shrink-0 mt-1" />
                  <div>
                    <h3 className="font-bold text-green-500 uppercase">Credential Minted Successfully</h3>
                    <p className="text-sm font-serif text-green-100/70 mt-1">
                      A Gold Tier credential has been issued to the user's DID and anchored on the blockchain.
                    </p>
                  </div>
                </div>

                <div className="space-y-3 font-mono text-xs overflow-hidden break-all">
                  <div className="p-3 bg-black/40 border border-white/10">
                    <span className="text-sidebar-primary block mb-1">Credential ID (URN):</span>
                    <span className="text-white/90">{issueResult.credential_id}</span>
                  </div>
                  
                  <div className="p-3 bg-black/40 border border-white/10">
                    <span className="text-sidebar-primary block mb-1">Document Hash (SHA-3):</span>
                    <span className="text-white/90">{issueResult.blockchain_anchor}</span>
                  </div>

                  <div className="p-3 bg-black/40 border border-white/10">
                    <span className="text-sidebar-primary flex items-center gap-1 mb-1">
                      <LinkIcon size={12} /> Blockchain Txn Hash:
                    </span>
                    <span className="text-white/90">{issueResult.txHash}</span>
                  </div>
                </div>
              </div>
            )}

            {issueResult && issueResult.status === "ERROR" && (
              <div className="bg-destructive/20 p-4 border-2 border-destructive rounded-none text-destructive-foreground">
                <h3 className="font-bold uppercase mb-1">Issuance Failed</h3>
                <p className="font-mono text-sm">{issueResult.message}</p>
              </div>
            )}

          </div>
        </div>
        
      </div>
    </div>
  );
}
