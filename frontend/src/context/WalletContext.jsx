import React, { createContext, useContext, useState, useEffect } from 'react';

const WalletContext = createContext();

export function WalletProvider({ children }) {
  const [credentials, setCredentials] = useState([]);
  const [did, setDid] = useState('');

  // Initialize from localStorage
  useEffect(() => {
    const saved = localStorage.getItem('astra_wallet_credentials');
    if (saved) {
      try {
        setCredentials(JSON.parse(saved));
      } catch (e) {
        console.error("Failed to parse credentials from local storage");
      }
    }
    
    let savedDid = localStorage.getItem('astra_wallet_did');
    if (!savedDid) {
      savedDid = `did:web:astraverify:user:${Math.random().toString(36).substr(2, 9)}`;
      localStorage.setItem('astra_wallet_did', savedDid);
    }
    setDid(savedDid);
  }, []);

  // Save to localStorage on change
  useEffect(() => {
    localStorage.setItem('astra_wallet_credentials', JSON.stringify(credentials));
  }, [credentials]);

  const addCredential = (cred) => {
    setCredentials((prev) => [...prev, { ...cred, id: Date.now().toString() }]);
  };

  const removeCredential = (id) => {
    setCredentials((prev) => prev.filter(c => c.id !== id));
  };

  const getCredential = (id) => {
    return credentials.find(c => c.id === id);
  };

  return (
    <WalletContext.Provider value={{ credentials, did, addCredential, removeCredential, getCredential }}>
      {children}
    </WalletContext.Provider>
  );
}

export function useWallet() {
  return useContext(WalletContext);
}
