"use client";

import { useState } from "react";
import { motion } from "framer-motion";

interface PasswordAuthProps {
  onAuthenticated: () => void;
}

export default function PasswordAuth({ onAuthenticated }: PasswordAuthProps) {
  const [password, setPassword] = useState("");
  const [isError, setIsError] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setIsError(false);
    setErrorMessage("");

    try {
      // Call the secure authentication API
      const response = await fetch('/api/auth', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ password }),
      });

      const data = await response.json();

      if (response.ok && data.success) {
        // Store the session token in localStorage
        localStorage.setItem('grace_session_token', data.token);
        localStorage.setItem('grace_session_expires', data.expiresAt);
        
        // Call the authenticated callback
        onAuthenticated();
      } else {
        setIsError(true);
        setErrorMessage(data.error || "Authentication failed");
        setPassword("");
      }
    } catch (error) {
      console.error('Authentication error:', error);
      setIsError(true);
      setErrorMessage("Connection error. Please try again.");
      setPassword("");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="h-full min-h-[100svh] flex items-center justify-center bg-white relative overflow-hidden">
      <div className="absolute inset-0 flex items-center justify-center z-0">
        <img 
          src="/background.png" 
          alt="AVA Background" 
          className="w-full h-full object-cover sm:object-contain opacity-10 grayscale"
          style={{ 
            imageRendering: 'crisp-edges'
          }}
        />
      </div>
      
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.09, 1.04, 0.245, 1.055] }}
        className="bg-white/90 backdrop-blur-sm rounded-lg p-6 sm:p-8 shadow-2xl border border-[#B9965B]/30 z-10 w-[calc(100%-2rem)] sm:w-96"
      >
        <div className="text-center mb-6">
          <h1 className="text-3xl font-heading font-bold text-[#B9965B] mb-2">AVA</h1>
          <p className="text-gray-600 font-body">Enter password to access</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              className={`w-full px-4 py-3 rounded-md bg-white border ${
                isError ? "border-red-400" : "border-gray-200"
              } text-black placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#B9965B]/50 focus:border-[#B9965B] transition-all font-body`}
              disabled={isLoading}
              autoFocus
            />
            {isError && (
              <motion.p
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="text-red-500 text-sm mt-2 font-body"
              >
                {errorMessage}
              </motion.p>
            )}
          </div>

          <button
            type="submit"
            disabled={isLoading || !password.trim()}
            className="w-full py-3 px-4 bg-[#B9965B] hover:bg-[#a3844e] disabled:bg-gray-300 disabled:cursor-not-allowed text-white rounded-md transition-colors duration-200 font-medium font-heading tracking-wide"
          >
            {isLoading ? "Authenticating..." : "Access AVA"}
          </button>
        </form>

        <div className="mt-4 text-center">
          <p className="text-gray-400 text-xs font-body">
            Secure authentication enabled
          </p>
        </div>
      </motion.div>
    </div>
  );
}