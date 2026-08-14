import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import LandingPage from './components/LandingPage';
import UserWallet from './components/UserWallet';
import VerifierPortal from './components/VerifierPortal';
import IssuerPortal from './components/IssuerPortal';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<LandingPage />} />
          <Route path="wallet/*" element={<UserWallet />} />
          <Route path="verifier/*" element={<VerifierPortal />} />
          <Route path="issuer/*" element={<IssuerPortal />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
