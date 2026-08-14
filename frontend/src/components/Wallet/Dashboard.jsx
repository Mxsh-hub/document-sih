import React from 'react';
import { useWallet } from '../../context/WalletContext';
import { Link } from 'react-router-dom';
import { FileText, ShieldAlert, ShieldCheck, Shield, ChevronRight } from 'lucide-react';

export default function Dashboard() {
  const { credentials, did } = useWallet();

  const getTierIcon = (tier) => {
    switch(tier) {
      case 'Gold': return <ShieldCheck className="text-accent" size={24} />;
      case 'Silver': return <Shield className="text-secondary" size={24} />;
      case 'Bronze': return <ShieldAlert className="text-[#cd7f32]" size={24} />;
      default: return <FileText size={24} />;
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
    <div className="space-y-8">
      <div className="neo-box p-6 bg-card flex flex-col md:flex-row justify-between items-center gap-4">
        <div>
          <h2 className="text-xl font-bold uppercase">Your Decentralized Identity</h2>
          <p className="font-mono text-sm bg-muted px-2 py-1 border-2 border-border mt-2 inline-block break-all">
            {did}
          </p>
        </div>
        <div className="text-right">
          <p className="text-sm font-bold text-muted-foreground uppercase">Total Credentials</p>
          <p className="text-4xl font-black">{credentials.length}</p>
        </div>
      </div>

      <div className="space-y-4">
        <div className="flex justify-between items-end border-b-4 border-border pb-2">
          <h3 className="text-2xl font-black uppercase">Stored Documents</h3>
          <Link to="/wallet/import" className="text-sm font-bold uppercase hover:underline decoration-2 decoration-primary underline-offset-4">
            + Add New
          </Link>
        </div>

        {credentials.length === 0 ? (
          <div className="neo-box p-12 bg-card border-dashed flex flex-col items-center text-center space-y-4">
            <div className="h-16 w-16 bg-muted border-2 border-border flex items-center justify-center">
              <FileText size={32} className="text-muted-foreground" />
            </div>
            <h4 className="text-xl font-bold">No credentials yet</h4>
            <p className="font-serif text-muted-foreground max-w-md">
              Your wallet is empty. Import a document from DigiLocker or upload a PDF to get started with privacy-first verification.
            </p>
            <Link to="/wallet/import" className="neo-button">
              Import Document
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {credentials.map((cred) => (
              <Link key={cred.id} to={`/wallet/credential/${cred.id}`} className="neo-box bg-card p-6 flex flex-col group cursor-pointer h-full">
                <div className="flex justify-between items-start mb-4">
                  <div className={`p-2 border-2 border-border shadow-neo-sm ${getTierBg(cred.tier)}`}>
                    {getTierIcon(cred.tier)}
                  </div>
                  <span className="font-mono text-xs font-bold px-2 py-1 border-2 border-border bg-background">
                    {cred.type || 'Document'}
                  </span>
                </div>
                
                <div className="flex-grow">
                  <h4 className="text-xl font-bold uppercase mb-2 group-hover:text-primary transition-colors line-clamp-2">
                    {cred.title}
                  </h4>
                  <p className="font-serif text-sm text-muted-foreground line-clamp-2">
                    Issued by: {cred.issuerName || 'Unknown'}
                  </p>
                </div>

                <div className="mt-6 pt-4 border-t-2 border-border flex justify-between items-center">
                  <span className={`text-xs font-black uppercase px-2 py-1 border-2 border-border ${getTierBg(cred.tier)}`}>
                    {cred.tier} Tier
                  </span>
                  <div className="bg-primary text-primary-foreground p-1 border-2 border-border group-hover:translate-x-1 transition-transform">
                    <ChevronRight size={16} />
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
