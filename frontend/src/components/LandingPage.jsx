import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Shield, Fingerprint, Lock, Zap, FileSearch, ArrowRight, BrainCircuit, Github, Twitter, CheckCircle2, XCircle, Building2 } from 'lucide-react';
import { motion } from 'framer-motion';

export default function LandingPage() {
  const [demoValue, setDemoValue] = useState(6.5);
  const threshold = 7.5;
  const isDemoValid = demoValue >= threshold;

  return (
    <div className="flex flex-col gap-24 py-12">
      {/* Hero Section */}
      <section className="flex flex-col lg:flex-row gap-12 items-center min-h-[70vh]">
        <motion.div 
          initial={{ opacity: 0, x: -50 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5 }}
          className="flex-1 space-y-8"
        >
          <div className="inline-block bg-accent text-accent-foreground font-mono font-bold px-4 py-1 border-2 border-border shadow-neo-sm transform -rotate-2 hover:rotate-0 transition-transform cursor-default">
            Smart India Hackathon 2026
          </div>
          <h1 className="text-6xl md:text-8xl font-black font-sans uppercase leading-none tracking-tight">
            Trust<br/>
            <span className="text-primary" style={{ textShadow: '6px 6px 0px var(--border)' }}>Zero-Knowledge.</span><br/>
            Verify Everything.
          </h1>
          <p className="text-xl md:text-2xl font-serif text-muted-foreground border-l-8 border-primary pl-6 max-w-2xl">
            AstraVerify is a privacy-first, AI-powered document verification platform enabling instant, cryptographic proof of credentials without exposing your raw data.
          </p>
          <div className="flex flex-wrap gap-6 pt-4">
            <Link to="/wallet" className="neo-button flex items-center gap-2 text-lg">
              <Fingerprint size={24} /> Access Wallet
            </Link>
            <Link to="/verifier" className="neo-button-accent flex items-center gap-2 text-lg">
              <FileSearch size={24} /> Verify Document
            </Link>
          </div>
        </motion.div>

        <motion.div 
          initial={{ opacity: 0, y: 50 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="flex-1 w-full"
        >
          <div className="neo-box aspect-square relative bg-secondary overflow-hidden group">
             <div className="absolute inset-0 flex items-center justify-center mix-blend-overlay opacity-30 group-hover:scale-110 transition-transform duration-700">
               <Shield size={350} strokeWidth={1} />
             </div>
             <div className="absolute inset-4 md:inset-8 border-4 border-border bg-card p-8 flex flex-col justify-between transform transition-transform group-hover:translate-x-2 group-hover:translate-y-2">
                <div className="flex justify-between items-start">
                  <motion.div 
                    animate={{ rotate: [0, 10, -10, 0] }}
                    transition={{ repeat: Infinity, duration: 4 }}
                    className="h-16 w-16 bg-primary rounded-full border-4 border-border shadow-neo-sm"
                  />
                  <span className="font-mono text-base font-bold bg-accent px-3 py-1 border-4 border-border shadow-neo-sm">did:web:astra</span>
                </div>
                <div className="space-y-6">
                  <div className="h-6 bg-muted border-2 border-border w-3/4"></div>
                  <div className="h-6 bg-muted border-2 border-border w-1/2"></div>
                  <div className="h-6 bg-muted border-2 border-border w-5/6"></div>
                </div>
                <div className="flex justify-between items-end border-t-8 border-border pt-6">
                   <div className="font-mono text-3xl font-black">VALIDATED</div>
                   <div className="bg-primary text-primary-foreground font-black text-xl px-6 py-3 border-4 border-border transform rotate-6 hover:rotate-0 transition-transform cursor-pointer shadow-neo">
                     ZKP GENERATED
                   </div>
                </div>
             </div>
          </div>
        </motion.div>
      </section>

      {/* Live ZK Demo */}
      <section className="space-y-8">
        <div className="flex flex-col items-center text-center space-y-4">
          <h2 className="text-4xl md:text-5xl font-black uppercase inline-block border-b-8 border-primary pb-2">Live ZKP Demo</h2>
          <p className="font-serif text-xl text-muted-foreground max-w-3xl">
            See Zero-Knowledge in action. Drag the slider to change your "Hidden CGPA". 
            The Verifier only sees the cryptographic YES/NO result—they never see your actual score.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-6xl mx-auto">
          {/* Prover Side */}
          <div className="neo-box p-8 bg-card space-y-8 relative overflow-hidden">
            <div className="absolute top-0 right-0 bg-primary text-primary-foreground font-bold px-4 py-1 border-b-2 border-l-2 border-border uppercase">Prover (You)</div>
            <h3 className="text-2xl font-bold uppercase mt-4">Your Private Data</h3>
            <p className="font-mono text-sm">This data stays on your device.</p>
            
            <div className="space-y-4">
              <div className="flex justify-between font-black text-xl">
                <span>My CGPA</span>
                <span className="text-primary">{demoValue.toFixed(1)}</span>
              </div>
              <input 
                type="range" 
                min="5.0" max="10.0" step="0.1" 
                value={demoValue} 
                onChange={(e) => setDemoValue(parseFloat(e.target.value))}
                className="w-full h-4 bg-muted border-2 border-border appearance-none cursor-pointer"
              />
              <div className="flex justify-between font-mono text-xs text-muted-foreground">
                <span>5.0</span>
                <span>10.0</span>
              </div>
            </div>

            <div className="p-4 bg-accent/20 border-2 border-accent border-dashed mt-8">
              <p className="font-mono text-xs break-all">
                {"{"}
                "pi_a": ["0x23ab...", "0x89fc..."],
                "pi_b": [["0x...", "0x..."], ...],
                "publicSignals": ["{isDemoValid ? "1" : "0"}"]
                {"}"}
              </p>
            </div>
          </div>

          {/* Verifier Side */}
          <div className="neo-box p-8 bg-sidebar text-sidebar-foreground space-y-8 relative overflow-hidden">
             <div className="absolute top-0 left-0 bg-accent text-accent-foreground font-bold px-4 py-1 border-b-2 border-r-2 border-border uppercase">Verifier (Employer)</div>
             <h3 className="text-2xl font-bold uppercase mt-4 text-sidebar-primary">Verifier Check</h3>
             <p className="font-mono text-sm text-sidebar-foreground/70">The verifier checks if: <strong>CGPA &gt;= 7.5</strong></p>
             
             <div className="flex-1 flex flex-col items-center justify-center h-48 mt-8">
                {isDemoValid ? (
                  <motion.div 
                    key="valid"
                    initial={{ scale: 0.5, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                    className="flex flex-col items-center text-green-500"
                  >
                    <CheckCircle2 size={80} className="mb-4" />
                    <span className="text-2xl font-black uppercase border-b-4 border-green-500">Mathematical Proof: VALID</span>
                    <p className="mt-4 text-center font-serif text-sidebar-foreground/70">The candidate proved their CGPA is &gt;= 7.5.<br/>(Actual CGPA remains secret).</p>
                  </motion.div>
                ) : (
                  <motion.div 
                    key="invalid"
                    initial={{ scale: 0.5, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                    className="flex flex-col items-center text-destructive"
                  >
                    <XCircle size={80} className="mb-4" />
                    <span className="text-2xl font-black uppercase border-b-4 border-destructive">Mathematical Proof: INVALID</span>
                    <p className="mt-4 text-center font-serif text-sidebar-foreground/70">The candidate failed to prove the constraint.<br/>(Actual CGPA remains secret).</p>
                  </motion.div>
                )}
             </div>
          </div>
        </div>
      </section>

      {/* How it Works Pipeline */}
      <section className="space-y-12">
        <h2 className="text-4xl md:text-5xl font-black uppercase text-center">The Architecture</h2>
        
        <div className="flex flex-col md:flex-row items-center justify-center gap-4 md:gap-0 relative">
          
          <div className="neo-box p-6 z-10 w-full md:w-1/4 text-center relative group">
            <div className="h-16 w-16 mx-auto !bg-primary text-primary-foreground flex items-center justify-center border-4 border-border shadow-neo mb-4 group-hover:rotate-12 transition-transform">
              <Building2 size={32} />
            </div>
            <h3 className="font-black uppercase mb-2">1. Ingest</h3>
            <p className="font-serif text-sm">OAuth with DigiLocker or Upload PDFs/Images.</p>
          </div>

          <ArrowRight className="hidden md:block text-primary mx-4 shrink-0" size={40} />
          
          <div className="neo-box p-6 z-10 w-full md:w-1/4 text-center relative group">
            <div className="h-16 w-16 mx-auto !bg-secondary text-secondary-foreground flex items-center justify-center border-4 border-border shadow-neo mb-4 group-hover:rotate-12 transition-transform">
              <BrainCircuit size={32} />
            </div>
            <h3 className="font-black uppercase mb-2">2. AI Swarm</h3>
            <p className="font-serif text-sm">Multi-agent analysis for forensics, deepfakes, & risk.</p>
          </div>

          <ArrowRight className="hidden md:block text-primary mx-4 shrink-0" size={40} />

          <div className="neo-box p-6 z-10 w-full md:w-1/4 text-center relative group">
            <div className="h-16 w-16 mx-auto !bg-accent text-accent-foreground flex items-center justify-center border-4 border-border shadow-neo mb-4 group-hover:rotate-12 transition-transform">
              <Lock size={32} />
            </div>
            <h3 className="font-black uppercase mb-2">3. Wallet ZKP</h3>
            <p className="font-serif text-sm">Generate Groth16 SnarkJS proofs entirely in-browser.</p>
          </div>

          <ArrowRight className="hidden md:block text-primary mx-4 shrink-0" size={40} />

          <div className="neo-box !bg-sidebar text-sidebar-foreground p-6 z-10 w-full md:w-1/4 text-center relative group">
            <div className="h-16 w-16 mx-auto !bg-primary text-primary-foreground flex items-center justify-center border-4 border-border shadow-neo mb-4 group-hover:rotate-12 transition-transform">
              <Shield size={32} />
            </div>
            <h3 className="font-black uppercase mb-2 text-sidebar-primary">4. Polygon</h3>
            <p className="font-serif text-sm text-sidebar-foreground/80">Verifiers mathematically validate and check anchor hash.</p>
          </div>

        </div>
      </section>

      {/* Tiered Trust Banner */}
      <section className="neo-box !bg-primary text-primary-foreground p-8 md:p-12 transform -rotate-1 hover:rotate-0 transition-transform">
        <div className="flex flex-col md:flex-row justify-between items-center gap-8">
           <div className="space-y-4 max-w-3xl">
             <h2 className="text-3xl md:text-5xl font-black uppercase">Tiered Trust Model</h2>
             <p className="font-mono text-xl">Not all documents are equal. AstraVerify classifies credentials into Gold, Silver, and Bronze tiers based on cryptographic origin and AI verification rigor.</p>
           </div>
           <Link to="/issuer" className="neo-button !bg-card !text-foreground hover:bg-card/90 whitespace-nowrap text-xl">
             Issuer Portal <ArrowRight className="inline ml-2" />
           </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t-8 border-border pt-12 pb-8 mt-12 flex flex-col items-center space-y-8">
        <div className="flex items-center gap-4 border-4 border-border p-4 bg-accent font-black uppercase text-2xl shadow-neo transform rotate-2">
          <Shield size={32} /> AstraVerify
        </div>
        <div className="flex gap-6 font-mono text-sm font-bold uppercase">
          <Link to="/wallet" className="hover:text-primary transition-colors">Wallet</Link>
          <Link to="/verifier" className="hover:text-primary transition-colors">Verifier</Link>
          <Link to="/issuer" className="hover:text-primary transition-colors">Issuer</Link>
          <a href="https://github.com/aruna/document-sih" target="_blank" rel="noreferrer" className="hover:text-primary transition-colors flex items-center gap-1">
            <Github size={16} /> GitHub
          </a>
        </div>
        <p className="font-serif text-muted-foreground text-sm text-center">
          Built for SIH 2026. Cryptography powered by snarkjs & circom.<br/>
          Deployed on local Polygon Hardhat node.
        </p>
      </footer>
    </div>
  );
}
