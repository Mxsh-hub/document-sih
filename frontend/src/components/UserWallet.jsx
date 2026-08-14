import React from 'react';
import { Routes, Route, Link, useLocation } from 'react-router-dom';
import { WalletProvider } from '../context/WalletContext';
import Dashboard from './Wallet/Dashboard';
import ImportOptions from './Wallet/ImportOptions';
import DocumentDetail from './Wallet/DocumentDetail';
import ZKProofGenerator from './Wallet/ZKProofGenerator';

export default function UserWallet() {
  const location = useLocation();

  return (
    <WalletProvider>
      <div className="flex flex-col gap-8">
        <header className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 border-b-4 border-border pb-4">
          <div>
            <h1 className="text-4xl font-black uppercase tracking-tight">User Wallet</h1>
            <p className="font-mono text-muted-foreground mt-2">Manage your privacy-first verifiable credentials.</p>
          </div>
          <nav className="flex gap-2">
            <Link 
              to="/wallet" 
              className={`px-4 py-2 font-bold border-2 border-border transition-colors ${location.pathname === '/wallet' ? 'bg-primary text-primary-foreground shadow-neo-sm translate-x-[2px] translate-y-[2px]' : 'bg-card hover:bg-muted'}`}
            >
              Dashboard
            </Link>
            <Link 
              to="/wallet/import" 
              className={`px-4 py-2 font-bold border-2 border-border transition-colors ${location.pathname === '/wallet/import' ? 'bg-primary text-primary-foreground shadow-neo-sm translate-x-[2px] translate-y-[2px]' : 'bg-card hover:bg-muted'}`}
            >
              Import Document
            </Link>
          </nav>
        </header>

        <main>
          <Routes>
            <Route index element={<Dashboard />} />
            <Route path="import" element={<ImportOptions />} />
            <Route path="credential/:id" element={<DocumentDetail />} />
            <Route path="prove/:id" element={<ZKProofGenerator />} />
          </Routes>
        </main>
      </div>
    </WalletProvider>
  );
}
