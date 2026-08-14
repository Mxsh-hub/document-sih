import React, { useState } from 'react';
import { Settings, FileSearch, Copy, Check } from 'lucide-react';

export default function CriteriaBuilder() {
  const [credentialType, setCredentialType] = useState('Degree');
  const [field, setField] = useState('cgpa');
  const [operator, setOperator] = useState('>');
  const [threshold, setThreshold] = useState('7.5');
  
  const [generatedRequest, setGeneratedRequest] = useState(null);
  const [copied, setCopied] = useState(false);

  const handleGenerate = (e) => {
    e.preventDefault();
    const requestPayload = {
      verifier: "did:web:employer.com",
      timestamp: new Date().toISOString(),
      requestedCredential: credentialType,
      constraint: {
        field,
        operator,
        value: parseFloat(threshold)
      }
    };
    setGeneratedRequest(JSON.stringify(requestPayload, null, 2));
    setCopied(false);
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(generatedRequest);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      <div className="flex items-center gap-4 border-b-4 border-border pb-4">
        <div className="p-3 bg-secondary text-secondary-foreground border-2 border-border shadow-neo-sm">
          <Settings size={32} />
        </div>
        <h2 className="text-3xl font-black uppercase">Criteria Builder</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        
        {/* Form */}
        <form onSubmit={handleGenerate} className="neo-box p-6 bg-card space-y-6">
          <div>
            <label className="block font-bold uppercase mb-2">Credential Type</label>
            <select 
              value={credentialType} 
              onChange={(e) => setCredentialType(e.target.value)}
              className="neo-input w-full"
            >
              <option value="Degree">B.Tech Degree</option>
              <option value="Identity">National Identity</option>
              <option value="Financial">Financial Statement</option>
            </select>
          </div>

          <div>
            <label className="block font-bold uppercase mb-2">Target Field</label>
            <select 
              value={field} 
              onChange={(e) => setField(e.target.value)}
              className="neo-input w-full"
            >
              <option value="cgpa">CGPA (Cumulative Grade Point Average)</option>
              <option value="age">Age</option>
              <option value="income">Annual Income</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block font-bold uppercase mb-2">Operator</label>
              <select 
                value={operator} 
                onChange={(e) => setOperator(e.target.value)}
                className="neo-input w-full"
              >
                <option value=">">Greater Than (&gt;)</option>
                <option value="<">Less Than (&lt;)</option>
                <option value=">=">Greater or Equal (&gt;=)</option>
              </select>
            </div>
            <div>
              <label className="block font-bold uppercase mb-2">Threshold</label>
              <input 
                type="number" 
                step="0.1"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
                className="neo-input w-full"
                required
              />
            </div>
          </div>

          <button type="submit" className="neo-button bg-secondary text-secondary-foreground hover:bg-secondary/90 w-full flex items-center justify-center gap-2">
            <FileSearch size={20} /> Generate Request Payload
          </button>
        </form>

        {/* Output */}
        <div className="neo-box bg-sidebar text-sidebar-foreground p-6 flex flex-col h-full">
          <div className="flex justify-between items-center mb-4 border-b-2 border-border pb-2">
            <h3 className="font-black uppercase text-xl text-primary">Generated JSON</h3>
            {generatedRequest && (
              <button onClick={handleCopy} className="flex items-center gap-1 text-sm font-bold hover:text-primary transition-colors">
                {copied ? <Check size={16} /> : <Copy size={16} />}
                {copied ? 'COPIED' : 'COPY'}
              </button>
            )}
          </div>
          
          {generatedRequest ? (
            <pre className="font-mono text-sm overflow-auto p-4 bg-background text-foreground border-2 border-border flex-1 shadow-inner">
              {generatedRequest}
            </pre>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center opacity-50">
               <FileSearch size={48} className="mb-4" />
               <p className="font-mono">Configure criteria and generate to see the JSON payload here.</p>
            </div>
          )}
          
          {generatedRequest && (
            <p className="font-serif text-sm mt-4 opacity-80">
              Provide this payload to the user (via DeepLink, QR Code, or Portal integration) so they can generate a Zero-Knowledge Proof using their local wallet.
            </p>
          )}
        </div>

      </div>
    </div>
  );
}
