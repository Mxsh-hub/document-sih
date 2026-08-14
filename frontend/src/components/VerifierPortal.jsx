import React from 'react';
import { Routes, Route, Link, useLocation } from 'react-router-dom';
import CriteriaBuilder from './Verifier/CriteriaBuilder';
import ProofValidator from './Verifier/ProofValidator';

export default function VerifierPortal() {
  const location = useLocation();

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 border-b-4 border-border pb-4">
        <div>
          <h1 className="text-4xl font-black uppercase tracking-tight text-secondary">Verifier Portal</h1>
          <p className="font-mono text-muted-foreground mt-2">Request and validate Zero-Knowledge Proofs instantly.</p>
        </div>
        <nav className="flex gap-2">
          <Link 
            to="/verifier" 
            className={`px-4 py-2 font-bold border-2 border-border transition-colors ${location.pathname === '/verifier' ? 'bg-secondary text-secondary-foreground shadow-neo-sm translate-x-[2px] translate-y-[2px]' : 'bg-card hover:bg-muted'}`}
          >
            Request Proof
          </Link>
          <Link 
            to="/verifier/validate" 
            className={`px-4 py-2 font-bold border-2 border-border transition-colors ${location.pathname === '/verifier/validate' ? 'bg-secondary text-secondary-foreground shadow-neo-sm translate-x-[2px] translate-y-[2px]' : 'bg-card hover:bg-muted'}`}
          >
            Validate Proof
          </Link>
        </nav>
      </header>

      <main>
        <Routes>
          <Route index element={<CriteriaBuilder />} />
          <Route path="validate" element={<ProofValidator />} />
        </Routes>
      </main>
    </div>
  );
}
