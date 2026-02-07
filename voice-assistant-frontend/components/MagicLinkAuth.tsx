"use client";

import { useState, useEffect } from "react";
import { 
  sendSignInLinkToEmail, 
  isSignInWithEmailLink, 
  signInWithEmailLink,
  User
} from "firebase/auth";
import { auth } from "@/lib/firebase";
import { motion } from "framer-motion";

interface MagicLinkAuthProps {
  userEmail: string;
  handoffId?: string;
  onAuthenticated: (user: User) => void;
}

export default function MagicLinkAuth({ userEmail: initialEmail, handoffId, onAuthenticated }: MagicLinkAuthProps) {
  const [email, setEmail] = useState(initialEmail);
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(60);

  useEffect(() => {
    if (isSignInWithEmailLink(auth, window.location.href)) {
      setLoading(true);
      
      const emailForSignIn = window.localStorage.getItem('emailForSignIn') || email;
      
      if (!emailForSignIn) {
        // No email available — user opened the link on a different browser/device.
        // The finishSignUp page handles this case with a proper form.
        setError('Please open this link in the same browser where you requested it.');
        setLoading(false);
        return;
      }
      
      signInWithEmailLink(auth, emailForSignIn, window.location.href)
        .then((result) => {
          window.localStorage.removeItem('emailForSignIn');
          onAuthenticated(result.user);
        })
        .catch((err) => {
          console.error('Magic link sign-in error:', err);
          setError('Link expired or invalid. Please request a new one.');
          setLoading(false);
        });
    }
  }, [onAuthenticated, email]);

  useEffect(() => {
    if (sent && countdown > 0) {
      const timer = setTimeout(() => setCountdown(c => c - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [sent, countdown]);

  const sendMagicLink = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!email) {
      setError("Please enter a valid email address");
      return;
    }

    setLoading(true);
    setError(null);
    
    try {
      // Get site_id from URL to preserve it in the magic link
      const params = new URLSearchParams(window.location.search);
      const siteId = params.get('site_id');
      
      // CRITICAL: Always use the AVA domain for the redirect URL, NOT window.location.origin.
      // In an iframe, window.location.origin is the EMBEDDING site (e.g. localhost:3019),
      // which Firebase will reject as unauthorized. The AVA domain IS in Firebase's
      // authorized domains list and is where the static export is actually hosted.
      const AVA_DOMAIN = process.env.NEXT_PUBLIC_AVA_DOMAIN || window.location.origin;
      const redirectParams = new URLSearchParams();
      // Always mark this as an embedded verification flow.
      // The magic link should open a confirmation-only page (no chat) and then be closed.
      redirectParams.set('embed', '1');
      redirectParams.set('site_id', siteId || 'default');

      // Include email in the URL so finishSignUp never needs to ask for it
      redirectParams.set('email', email);
      // Handoff id lets the original embedded iframe poll the backend and sign-in
      // inside the iframe's own storage partition (required in modern browsers).
      if (handoffId) redirectParams.set('handoff', handoffId);

      let redirectUrl = `${AVA_DOMAIN}/embed/finishSignUp?${redirectParams.toString()}`;
      
      console.log("Magic Link Redirect URL:", redirectUrl);

      const actionCodeSettings = {
        url: redirectUrl,
        handleCodeInApp: true,
      };

      // Check if we are in an iframe
      const isIframe = window.parent !== window;
      
      if (isIframe) {
        console.log("Sending magic link from iframe context");
      }

      await sendSignInLinkToEmail(auth, email, actionCodeSettings);
      
      window.localStorage.setItem('emailForSignIn', email);
      
      setSent(true);
      setCountdown(60);
    } catch (err: any) {
      console.error('Failed to send magic link:', err);
      setError(err.message || 'Failed to send verification email');
    } finally {
      setLoading(false);
    }
  };

  if (loading && isSignInWithEmailLink(auth, window.location.href)) {
    return (
      <div className="h-full flex items-center justify-center bg-white">
        <div className="text-[#B9965B] font-heading text-xl">Apparaat verifiëren...</div>
      </div>
    );
  }

  return (
    <div className="h-full min-h-[100svh] flex items-center justify-center bg-white relative">
      <div className="absolute inset-0 flex items-center justify-center z-0 overflow-hidden">
        <img 
          src="/background.png" 
          alt="AVA Background" 
          className="opacity-90 w-full h-full object-cover sm:object-contain"
          style={{ imageRendering: 'crisp-edges' }}
        />
      </div>
      
      <motion.div 
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="z-10 bg-white/90 backdrop-blur-md p-8 rounded-xl shadow-2xl border border-[#B9965B]/30 w-[calc(100%-2rem)] sm:w-96 text-center"
      >
        <h2 className="text-3xl font-heading font-bold text-[#B9965B] mb-2">Apparaat Verificatie</h2>
        
        {!sent ? (
          <form onSubmit={sendMagicLink}>
            <p className="text-gray-600 mb-6 font-body">
              {initialEmail 
                ? "Om toegang te krijgen tot je beveiligde chat, moeten we dit apparaat eenmalig verifiëren. We sturen een link naar:"
                : "Voer je e-mailadres in om een verificatielink te ontvangen voor dit apparaat."}
            </p>
            
            {initialEmail ? (
              <div className="bg-gray-50 p-3 rounded-lg mb-6 font-mono text-sm text-gray-700">
                {initialEmail}
              </div>
            ) : (
              <div className="mb-6">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="jouw@email.com"
                  required
                  className="w-full p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#B9965B] font-body"
                />
              </div>
            )}
            
            {error && (
              <div className="mb-4 p-3 bg-red-50 text-red-600 text-sm rounded-lg border border-red-100">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !email}
              className="w-full py-3 px-6 bg-[#B9965B] hover:bg-[#A8854A] text-white rounded-lg font-body font-medium transition-all disabled:opacity-50"
            >
              {loading ? 'Verzenden...' : 'Stuur Magic Link'}
            </button>
            
            <p className="mt-6 text-xs text-gray-400 font-body">
              Je hoeft dit de komende 180 dagen niet opnieuw te doen op dit apparaat.
            </p>
          </form>
        ) : (
          <>
            <div className="mb-6">
              <svg className="w-16 h-16 mx-auto text-[#B9965B]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            
            <p className="text-gray-600 mb-4 font-body">
              We hebben een magic link gestuurd naar:<br/>
              <strong>{email}</strong>
            </p>
            
            <div className="text-sm text-gray-500 mb-6 space-y-3">
              <p>
                Klik op de link in je e-mail om dit apparaat te verifiëren.<br/>
                <span className="text-amber-600 font-medium">Je kunt de link in een nieuw tabblad openen; dit venster wordt automatisch bijgewerkt.</span>
              </p>
              
              <div className="bg-gray-50 p-3 rounded-lg text-xs border border-gray-100">
                <p className="font-medium text-gray-600 mb-1">Geen mail ontvangen?</p>
                <ul className="list-disc list-inside text-left space-y-1">
                  <li>Check je <strong>spam-folder</strong>.</li>
                  <li>De afzender is: <code className="bg-gray-100 px-1 rounded">noreply@ai-chatbot-v1-645d6.firebaseapp.com</code></li>
                </ul>
              </div>
            </div>
            
            {countdown > 0 ? (
              <p className="text-xs text-gray-400">
                Opnieuw verzenden mogelijk over {countdown}s
              </p>
            ) : (
              <button
                type="button"
                onClick={() => sendMagicLink()}
                className="text-[#B9965B] hover:text-[#A8854A] text-sm underline"
              >
                Magic Link opnieuw verzenden
              </button>
            )}
          </>
        )}
      </motion.div>
    </div>
  );
}
