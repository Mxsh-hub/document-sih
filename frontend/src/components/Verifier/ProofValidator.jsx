import React, { useState } from 'react';
import { ShieldCheck, ShieldAlert, FileKey, Loader2, Link as LinkIcon } from 'lucide-react';
import { ethers } from 'ethers';

export default function ProofValidator() {
  const [proofInput, setProofInput] = useState('');
  const [isValidating, setIsValidating] = useState(false);
  const [validationResult, setValidationResult] = useState(null);

  const contractAddress = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512";
  // Minimal ABI for verifyZKProof
  const contractABI = [
    "function verifyZKProof(uint256[2] _pA, uint256[2][2] _pB, uint256[2] _pC, uint256[1] _pubSignals, bytes32 _docHash) external returns (bool)"
  ];

  const handleValidate = async (e) => {
    e.preventDefault();
    if (!proofInput.trim()) return;

    setIsValidating(true);
    setValidationResult(null);

    try {
      // 1. Parse Input
      const parsedInput = JSON.parse(proofInput);
      const { pi_a, pi_b, pi_c, protocol, curve, publicSignals, docHash } = parsedInput;

      const proof = { pi_a, pi_b, pi_c, protocol, curve };

      // 2. Fetch Verification Key
      const vKeyRes = await fetch('/circuits/verification_key.json');
      const vKey = await vKeyRes.json();

      // 3. Cryptographic Verification (snarkjs)
      const res = await window.snarkjs.groth16.verify(vKey, publicSignals, proof);
      
      if (!res) {
        throw new Error("Invalid ZK Proof: Mathematical constraint failed.");
      }

      let blockchainStatus = "Mathematical Verification Passed. (No blockchain check performed)";
      let txHash = "N/A";

      // 4. Blockchain Verification (ethers)
      if (docHash && ethers) {
        try {
          // Connect to local Hardhat node
          const provider = new ethers.JsonRpcProvider("http://127.0.0.1:8545");
          const signer = await provider.getSigner(0); // Use first account
          
          const contract = new ethers.Contract(contractAddress, contractABI, signer);
          
          // Format pi_b for Solidity (reverse inner arrays)
          const pA = [proof.pi_a[0], proof.pi_a[1]];
          const pB = [
            [proof.pi_b[0][1], proof.pi_b[0][0]],
            [proof.pi_b[1][1], proof.pi_b[1][0]]
          ];
          const pC = [proof.pi_c[0], proof.pi_c[1]];

          // This will throw if document is not anchored
          const tx = await contract.verifyZKProof(pA, pB, pC, publicSignals, docHash);
          await tx.wait();
          
          blockchainStatus = "Anchored and Verified on Polygon (Localhost)";
          txHash = tx.hash;
        } catch (bcError) {
           console.error("Blockchain verification error:", bcError);
           blockchainStatus = "Mathematical Verification Passed, but Blockchain anchor check failed.";
        }
      }

      setValidationResult({
        valid: true,
        signals: {
          "1": publicSignals[0] === "1" ? "TRUE (Condition Met)" : "FALSE"
        },
        blockchainStatus,
        txHash,
        timestamp: new Date().toISOString()
      });

    } catch (err) {
      console.error(err);
      setValidationResult({
        valid: false,
        error: err.message || "Invalid proof structure or failed mathematical verification."
      });
    } finally {
      setIsValidating(false);
    }
  };

  const loadSampleProof = () => {
    // This is just a structurally correct mock to test parsing.
    // For a real mathematical success, generate a real proof from the Wallet and paste it.
    const sample = {
      pi_a: ["1", "2", "3"],
      pi_b: [["1", "2"], ["3", "4"], ["5", "6"]],
      pi_c: ["1", "2", "3"],
      protocol: "groth16",
      curve: "bn128",
      publicSignals: ["1"],
      docHash: "0x" + "00".repeat(32) // Example bytes32
    };
    setProofInput(JSON.stringify(sample, null, 2));
  };

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      <div className="flex items-center gap-4 border-b-4 border-border pb-4">
        <div className="p-3 bg-primary text-primary-foreground border-2 border-border shadow-neo-sm">
          <FileKey size={32} />
        </div>
        <h2 className="text-3xl font-black uppercase">Proof Validator</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        
        {/* Input Form */}
        <div className="neo-box p-6 bg-card flex flex-col h-full">
          <div className="flex justify-between items-center mb-4">
            <h3 className="font-bold uppercase">Submit ZK Proof</h3>
            <button onClick={loadSampleProof} className="text-xs font-bold underline decoration-2 decoration-secondary hover:text-secondary transition-colors">
              Load Sample
            </button>
          </div>
          <form onSubmit={handleValidate} className="flex flex-col flex-1 gap-4">
            <textarea 
              className="neo-input flex-1 min-h-[250px] resize-none text-xs"
              placeholder="Paste the Groth16 JSON proof payload here..."
              value={proofInput}
              onChange={(e) => setProofInput(e.target.value)}
              required
            ></textarea>
            <button type="submit" disabled={isValidating} className="neo-button bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed">
              {isValidating ? (
                <span className="flex items-center justify-center gap-2"><Loader2 size={20} className="animate-spin" /> Verifying Math...</span>
              ) : 'Cryptographically Verify'}
            </button>
          </form>
        </div>

        {/* Results Panel */}
        <div className="neo-box p-6 bg-muted border-dashed flex flex-col">
          <h3 className="font-bold uppercase mb-4 border-b-2 border-border pb-2">Verification Result</h3>
          
          {!validationResult && !isValidating && (
             <div className="flex-1 flex flex-col items-center justify-center text-center opacity-50">
               <ShieldCheck size={48} className="mb-4 text-muted-foreground" />
               <p className="font-mono text-sm">Awaiting proof submission.<br/>Validation uses snarkjs.</p>
             </div>
          )}

          {isValidating && (
             <div className="flex-1 flex flex-col items-center justify-center text-center">
               <Loader2 size={48} className="mb-4 animate-spin text-secondary" />
               <p className="font-black uppercase animate-pulse">Checking Groth16 Constraints...</p>
             </div>
          )}

          {validationResult && validationResult.valid && (
            <div className="flex-1 flex flex-col space-y-6">
              <div className="bg-[#f0fff4] border-2 border-border p-4 flex items-start gap-4">
                <ShieldCheck className="text-[#008f4c] shrink-0 mt-1" size={32} />
                <div>
                  <h4 className="font-black uppercase text-[#008f4c] text-xl">Proof is Valid</h4>
                  <p className="font-mono text-xs text-muted-foreground mt-1">Mathematical verification passed. The underlying constraints are satisfied.</p>
                </div>
              </div>

              <div className="space-y-2">
                 <span className="font-mono text-xs uppercase font-bold">Public Signals Evaluated</span>
                 <div className="bg-card border-2 border-border p-3 font-mono text-sm">
                   Signal [0] (Result) = <span className="font-black text-secondary">{validationResult.signals["1"]}</span>
                 </div>
              </div>

              <div className="space-y-2">
                 <span className="font-mono text-xs uppercase font-bold">Blockchain Anchoring</span>
                 <div className="bg-sidebar text-sidebar-foreground border-2 border-border p-4">
                   <div className="flex items-center justify-between mb-2">
                     <span className="font-bold text-sm text-primary">{validationResult.blockchainStatus}</span>
                     <LinkIcon size={16} />
                   </div>
                   <p className="font-mono text-xs opacity-70 break-all">Tx: {validationResult.txHash}</p>
                 </div>
              </div>
            </div>
          )}

          {validationResult && !validationResult.valid && (
            <div className="flex-1 flex flex-col">
              <div className="bg-[#fff0f0] border-2 border-border p-4 flex items-start gap-4">
                <ShieldAlert className="text-destructive shrink-0 mt-1" size={32} />
                <div>
                  <h4 className="font-black uppercase text-destructive text-xl">Verification Failed</h4>
                  <p className="font-mono text-xs text-muted-foreground mt-1">{validationResult.error}</p>
                </div>
              </div>
            </div>
          )}

        </div>

      </div>
    </div>
  );
}
