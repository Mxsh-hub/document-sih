import React from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useWallet } from '../../context/WalletContext';
import { ArrowLeft, ShieldCheck, Shield, ShieldAlert, Fingerprint, Trash2, CheckCircle2 } from 'lucide-react';

export default function DocumentDetail() {
  const { id } = useParams();
  const { getCredential, removeCredential } = useWallet();
  const navigate = useNavigate();
  
  const cred = getCredential(id);

  if (!cred) {
    return (
      <div className="neo-box p-8 bg-card text-center">
        <h2 className="text-2xl font-bold">Credential Not Found</h2>
        <Link to="/wallet" className="neo-button mt-4 inline-block">Back to Dashboard</Link>
      </div>
    );
  }

  const handleDelete = () => {
    if (window.confirm('Are you sure you want to permanently delete this credential from your wallet?')) {
      removeCredential(cred.id);
      navigate('/wallet');
    }
  };

  const getTierIcon = (tier) => {
    switch(tier) {
      case 'Gold': return <ShieldCheck className="text-accent" size={32} />;
      case 'Silver': return <Shield className="text-secondary" size={32} />;
      case 'Bronze': return <ShieldAlert className="text-[#cd7f32]" size={32} />;
      default: return null;
    }
  };

  const getTierBg = (tier) => {
    switch(tier) {
      case 'Gold': return 'bg-accent text-accent-foreground';
      case 'Silver': return 'bg-secondary text-secondary-foreground';
      case 'Bronze': return 'bg-[#cd7f32] text-white';
      default: return 'bg-muted text-muted-foreground';
    }
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex justify-between items-center border-b-4 border-border pb-4">
        <Link to="/wallet" className="flex items-center gap-2 font-bold hover:underline decoration-2 decoration-primary underline-offset-4">
          <ArrowLeft size={20} /> Back
        </Link>
        <button onClick={handleDelete} className="flex items-center gap-2 text-destructive font-bold hover:underline decoration-2 decoration-destructive underline-offset-4">
          <Trash2 size={20} /> Delete
        </button>
      </div>

      <div className="neo-box bg-card p-8 space-y-8">
        
        {/* Header */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
           <div>
             <div className="flex items-center gap-4 mb-2">
               <div className={`p-3 border-2 border-border shadow-neo-sm ${getTierBg(cred.tier)}`}>
                  {getTierIcon(cred.tier)}
               </div>
               <span className="font-mono text-sm font-bold px-2 py-1 border-2 border-border bg-background uppercase">
                 {cred.type || 'Document'}
               </span>
             </div>
             <h2 className="text-3xl font-black uppercase mt-4">{cred.title}</h2>
             <p className="font-serif text-muted-foreground text-lg">Issued by: <span className="font-bold text-foreground">{cred.issuerName}</span></p>
           </div>
           
           <div className={`px-4 py-2 border-2 border-border font-black uppercase text-xl transform rotate-3 shadow-neo ${getTierBg(cred.tier)}`}>
             {cred.tier} TIER
           </div>
        </div>

        {/* Payload / Metadata */}
        <div className="space-y-4">
          <h3 className="text-xl font-bold uppercase border-b-2 border-border pb-2">Document Payload</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
             {Object.entries(cred.metadata || {}).map(([key, value]) => (
               <div key={key} className="p-4 border-2 border-border bg-muted flex flex-col">
                  <span className="font-mono text-xs uppercase text-muted-foreground font-bold mb-1">{key}</span>
                  <span className="font-sans font-bold text-lg">{value}</span>
               </div>
             ))}
          </div>
        </div>

        {/* AI Swarm Report (if applicable) */}
        {cred.aiReport && (
          <div className="space-y-4">
            <h3 className="text-xl font-bold uppercase border-b-2 border-border pb-2 flex items-center gap-2">
              <Fingerprint size={24} /> AI Swarm Forensics
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {Object.entries(cred.aiReport).map(([agent, report]) => (
                <div key={agent} className={`p-4 border-2 border-border flex flex-col ${report.passed ? 'bg-[#f0fff4]' : 'bg-[#fff0f0]'}`}>
                  <div className="flex justify-between items-start mb-2">
                    <span className="font-black uppercase text-sm">{agent} Agent</span>
                    {report.passed ? <CheckCircle2 className="text-[#008f4c]" size={20} /> : <ShieldAlert className="text-destructive" size={20} />}
                  </div>
                  <div className="text-2xl font-mono font-bold mb-2">{report.score}/100</div>
                  <p className="font-serif text-xs text-muted-foreground">{report.details}</p>
                </div>
              ))}
            </div>
          </div>
        )}
        
        {/* Actions */}
        <div className="pt-8 border-t-4 border-border flex justify-end">
          <Link to={`/wallet/prove/${cred.id}`} className="neo-button bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-2">
            Generate Zero-Knowledge Proof <ArrowLeft className="rotate-180" size={20} />
          </Link>
        </div>

      </div>
    </div>
  );
}
