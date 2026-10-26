import React from 'react';
import { Outlet, Link } from 'react-router-dom';
import { ShieldCheck, User, Building, FileCheck, ClipboardCheck } from 'lucide-react';

export default function Layout() {
  return (
    <div className="min-h-screen flex flex-col">
      <nav className="neo-box border-b-4 border-border px-6 py-4 flex justify-between items-center sticky top-0 z-50 bg-card rounded-none">
        <Link to="/" className="flex items-center gap-2">
          <div className="bg-primary text-primary-foreground p-2 border-2 border-border neo-box hover:translate-x-0 hover:translate-y-0 hover:shadow-neo">
            <ShieldCheck size={28} strokeWidth={2.5} />
          </div>
          <span className="font-bold text-2xl tracking-tight">ASTRAVERIFY</span>
        </Link>
        
        <div className="flex gap-4">
          <Link to="/wallet" className="flex items-center gap-2 font-bold px-4 py-2 border-2 border-border hover:bg-muted transition-colors">
            <User size={18} /> Wallet
          </Link>
          <Link to="/verifier" className="flex items-center gap-2 font-bold px-4 py-2 border-2 border-border hover:bg-muted transition-colors">
            <FileCheck size={18} /> Verifier
          </Link>
          <Link to="/issuer" className="flex items-center gap-2 font-bold px-4 py-2 border-2 border-border bg-accent text-accent-foreground hover:bg-accent/90 transition-colors">
            <Building size={18} /> Issuer
          </Link>
          <Link to="/compliance" className="flex items-center gap-2 font-bold px-4 py-2 border-2 border-border bg-primary text-primary-foreground hover:bg-primary/90 transition-colors">
            <ClipboardCheck size={18} /> Compliance
          </Link>
        </div>
      </nav>

      <main className="flex-1 p-6 max-w-7xl mx-auto w-full">
        <Outlet />
      </main>

      <footer className="neo-box border-t-4 border-border p-6 mt-12 bg-sidebar text-sidebar-foreground">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center font-mono text-sm">
          <p>© 2026 AstraVerify - Smart India Hackathon. Privacy-First ZK Verification.</p>
          <div className="flex gap-6 mt-4 md:mt-0">
            <a href="#" className="hover:underline underline-offset-4 decoration-2 decoration-accent">Github</a>
            <a href="#" className="hover:underline underline-offset-4 decoration-2 decoration-accent">Documentation</a>
            <a href="#" className="hover:underline underline-offset-4 decoration-2 decoration-accent">Ministry of Power</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
