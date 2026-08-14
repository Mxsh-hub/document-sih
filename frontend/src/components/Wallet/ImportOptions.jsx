import React, { useState, useCallback } from 'react';
import { useWallet } from '../../context/WalletContext';
import { useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import { Cloud, FileUp, Camera, Loader2 } from 'lucide-react';
import axios from 'axios';

export default function ImportOptions() {
  const { addCredential } = useWallet();
  const navigate = useNavigate();
  const [isUploading, setIsUploading] = useState(false);

  const handleDigilocker = () => {
    // In a real flow, this redirects to DigiLocker OAuth URL
    // For now, simulate adding a Gold credential
    setIsUploading(true);
    setTimeout(() => {
      addCredential({
        title: "B.Tech Degree Certificate",
        type: "Degree",
        issuerName: "National Institute of Technology",
        tier: "Gold",
        dateAdded: new Date().toISOString(),
        metadata: {
          cgpa: 8.5,
          year: "2024",
          major: "Computer Science"
        }
      });
      setIsUploading(false);
      navigate('/wallet');
    }, 1500);
  };

  const onDrop = useCallback(async (acceptedFiles) => {
    const file = acceptedFiles[0];
    if (!file) return;

    setIsUploading(true);
    
    // Simulate API call to FastAPI backend for AI Swarm analysis
    setTimeout(() => {
      addCredential({
        title: file.name,
        type: "Uploaded PDF",
        issuerName: "Unknown / Attested via AI",
        tier: "Silver",
        dateAdded: new Date().toISOString(),
        metadata: {
          cgpa: 7.8, // Mocked extracted data
          year: "2023"
        },
        aiReport: {
          forensics: { passed: true, score: 98, details: "Font metadata consistent." },
          deepfake: { passed: true, score: 95, details: "No synthetic artifacts detected." },
          risk: { passed: true, score: 99, details: "IP and geolocation match." }
        }
      });
      setIsUploading(false);
      navigate('/wallet');
    }, 3000);
  }, [addCredential, navigate]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    multiple: false
  });

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      <h2 className="text-3xl font-black uppercase border-b-4 border-border pb-4">Import Document</h2>
      
      {isUploading && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center">
          <div className="neo-box p-8 bg-card flex flex-col items-center text-center space-y-4">
             <Loader2 size={48} className="animate-spin text-primary" />
             <h3 className="text-xl font-bold uppercase">Processing...</h3>
             <p className="font-mono text-sm">Running AI Swarm analysis and cryptographic attestation.</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        
        {/* DigiLocker Option */}
        <div className="neo-box p-6 bg-accent text-accent-foreground flex flex-col items-center text-center space-y-4 justify-between h-full hover:-translate-y-2 transition-transform cursor-pointer" onClick={handleDigilocker}>
          <div className="p-4 bg-card text-foreground border-2 border-border shadow-neo-sm">
            <Cloud size={48} />
          </div>
          <div>
            <h3 className="text-2xl font-black uppercase mb-2">DigiLocker</h3>
            <p className="font-serif text-sm">Import natively verified documents. Guaranteed Gold Tier.</p>
          </div>
          <button className="neo-button w-full mt-4 bg-card text-foreground hover:bg-card/90">
            Connect
          </button>
        </div>

        {/* PDF Upload Option */}
        <div 
          {...getRootProps()}
          className={`neo-box p-6 bg-card flex flex-col items-center text-center space-y-4 justify-between h-full cursor-pointer transition-colors ${isDragActive ? 'bg-muted' : ''}`}
        >
          <input {...getInputProps()} />
          <div className="p-4 bg-secondary text-secondary-foreground border-2 border-border shadow-neo-sm">
            <FileUp size={48} />
          </div>
          <div>
            <h3 className="text-2xl font-black uppercase mb-2">Upload PDF</h3>
            <p className="font-serif text-sm">AI Swarm will forensically analyze the file for Silver Tier attestation.</p>
          </div>
          <button className="neo-button w-full mt-4 bg-secondary text-secondary-foreground hover:bg-secondary/90 pointer-events-none">
            {isDragActive ? 'Drop Here' : 'Select PDF'}
          </button>
        </div>

        {/* Camera Option */}
        <div className="neo-box p-6 bg-sidebar text-sidebar-foreground flex flex-col items-center text-center space-y-4 justify-between h-full hover:-translate-y-2 transition-transform cursor-not-allowed opacity-80">
          <div className="p-4 bg-card text-foreground border-2 border-border shadow-neo-sm">
            <Camera size={48} />
          </div>
          <div>
            <h3 className="text-2xl font-black uppercase mb-2">Scan Photo</h3>
            <p className="font-serif text-sm">Take a photo of a physical document. Bronze Tier (OCR only).</p>
          </div>
          <button className="neo-button w-full mt-4 bg-card text-foreground hover:bg-card/90" disabled>
            Coming Soon
          </button>
        </div>

      </div>
    </div>
  );
}
