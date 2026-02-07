"use client";

import { useEffect, useState } from "react";
import { isSignInWithEmailLink, signInWithEmailLink } from "firebase/auth";
import { auth } from "@/lib/firebase";
import { useRouter, useSearchParams } from "next/navigation";
import { exchangeForDeviceToken } from "@/lib/deviceToken";

export default function FinishSignUpPage() {
  const [status, setStatus] = useState<'verifying' | 'success' | 'error' | 'needs_email'>('verifying');
  const [error, setError] = useState<string>('');
  const [isEmbeddedSession, setIsEmbeddedSession] = useState(false);
  const [manualEmail, setManualEmail] = useState('');
  const [showFallbackLink, setShowFallbackLink] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();

  const completeSignIn = async (email: string) => {
    try {
      setStatus('verifying');
      const result = await signInWithEmailLink(auth, email, window.location.href);
      window.localStorage.removeItem('emailForSignIn');

      // Set the device token cookie so the user stays logged in
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "https://token.makecontact.io";
      const siteId = searchParams.get('site_id') || 'default';
      const handoff = searchParams.get('handoff');
      try {
        const idToken = await result.user.getIdToken();
        await exchangeForDeviceToken(backendUrl, idToken, siteId);

        // Complete auth handoff so the *original embedded iframe* can sign-in inside its own
        // storage partition (needed when embedded cross-site).
        if (handoff) {
          await fetch(`${backendUrl}/api/auth-handoff/complete`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${idToken}`,
            },
            body: JSON.stringify({ handoffId: handoff, siteId }),
          });
        }
      } catch (e) {
        console.warn('Device token exchange failed (non-blocking):', e);
      }
      
      // Broadcast success to the original tab/iframe
      if (typeof BroadcastChannel !== 'undefined') {
        const channel = new BroadcastChannel('ava_auth');
        channel.postMessage({ type: 'AUTH_SUCCESS', uid: result.user.uid });
        channel.close();
      }

      const embedFlag = searchParams.get('embed') === '1';
      const isEmbedded = embedFlag || !!(siteId && siteId !== 'default');

      setStatus('success');
      setIsEmbeddedSession(isEmbedded);

      // IMPORTANT: never auto-open chat from the magic link tab.
      // This page is confirmation-only; user should close it.
      // (Browsers may block programmatic closing, so we show instructions.)
    } catch (err: any) {
      console.error('Sign-in error:', err);
      setStatus('error');
      setError(err.message || 'Verificatie mislukt. De link is mogelijk verlopen.');
    }
  };

  useEffect(() => {
    if (status !== 'success') return;
    // Best-effort: most browsers block window.close() for tabs opened from email links.
    // Still try; if blocked, user will see the close-tab instructions.
    const timer = setTimeout(() => {
      try { window.close(); } catch { /* ignore */ }
    }, 800);
    return () => clearTimeout(timer);
  }, [status]);

  // If the browser blocks auto-close and the embedded page somehow doesn't update,
  // show a fallback link after 5 seconds.
  useEffect(() => {
    if (status !== 'success') return;
    const t = setTimeout(() => setShowFallbackLink(true), 5000);
    return () => clearTimeout(t);
  }, [status]);

  useEffect(() => {
    if (!isSignInWithEmailLink(auth, window.location.href)) {
      setStatus('error');
      setError('Ongeldige of verlopen link. Vraag een nieuwe magic link aan.');
      return;
    }

    // Get email from: 1) URL param (always present), 2) localStorage (same browser), 3) ask user
    const emailFromUrl = searchParams.get('email');
    const emailFromStorage = window.localStorage.getItem('emailForSignIn');
    const email = emailFromUrl || emailFromStorage;
    
    if (email) {
      completeSignIn(email);
    } else {
      setStatus('needs_email');
    }
  }, [router, searchParams]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-white to-gray-50">
      <div className="text-center p-8 max-w-md mx-auto">

        {status === 'verifying' && (
          <>
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#B9965B] mx-auto mb-6"></div>
            <h2 className="text-xl font-heading text-[#B9965B]">Even geduld...</h2>
            <p className="text-gray-500 mt-2 text-sm">Je apparaat wordt geverifieerd.</p>
          </>
        )}
        
        {status === 'success' && (
          <>
            <svg className="w-20 h-20 mx-auto text-green-500 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <h2 className="text-2xl font-heading font-bold text-[#B9965B] mb-3">Verificatie geslaagd!</h2>
            
            {isEmbeddedSession ? (
              <div className="space-y-4">
                <p className="text-gray-600 leading-relaxed">
                  Je apparaat is succesvol gekoppeld. Je hoeft dit de komende 180 dagen niet opnieuw te doen.
                </p>
                <div className="bg-[#B9965B]/10 border border-[#B9965B]/20 rounded-lg p-4 mt-4">
                  <p className="text-[#B9965B] font-medium text-sm">
                    Je kunt dit tabblad nu sluiten.
                  </p>
                  <p className="text-gray-500 text-xs mt-1">
                    Het chatvenster op de oorspronkelijke pagina is nu actief.
                  </p>
                </div>
                {showFallbackLink && (
                  <div className="text-xs text-gray-500 pt-2">
                    Lukt het niet automatisch?{" "}
                    <a
                      className="underline text-[#B9965B]"
                      href={`${process.env.NEXT_PUBLIC_AVA_DOMAIN || ''}/embed?site_id=${encodeURIComponent(searchParams.get('site_id') || 'default')}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open de chat
                    </a>
                    .
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                <p className="text-gray-600 leading-relaxed">
                  Je bent ingelogd en je apparaat is gekoppeld.
                </p>
                <div className="bg-[#B9965B]/10 border border-[#B9965B]/20 rounded-lg p-4 mt-4">
                  <p className="text-[#B9965B] font-medium text-sm">
                    Je kunt dit tabblad nu sluiten.
                  </p>
                </div>
                {showFallbackLink && (
                  <div className="text-xs text-gray-500 pt-2">
                    <a
                      className="underline text-[#B9965B]"
                      href={`${process.env.NEXT_PUBLIC_AVA_DOMAIN || ''}/embed`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open de chat
                    </a>
                  </div>
                )}
              </div>
            )}
          </>
        )}
        
        {status === 'needs_email' && (
          <form onSubmit={(e) => { e.preventDefault(); if (manualEmail) completeSignIn(manualEmail); }} className="max-w-sm mx-auto">
            <svg className="w-16 h-16 mx-auto text-[#B9965B] mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            <h2 className="text-xl font-heading text-[#B9965B] mb-2">Bevestig je e-mail</h2>
            <p className="text-gray-600 mb-4 text-sm">
              Voer het e-mailadres in waarmee je de magic link hebt aangevraagd.
            </p>
            <input
              type="email"
              value={manualEmail}
              onChange={(e) => setManualEmail(e.target.value)}
              placeholder="jouw@email.com"
              required
              className="w-full p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#B9965B] mb-4"
            />
            <button
              type="submit"
              disabled={!manualEmail}
              className="w-full py-3 px-6 bg-[#B9965B] hover:bg-[#A8854A] text-white rounded-lg font-medium transition-all disabled:opacity-50"
            >
              Verifieer
            </button>
          </form>
        )}

        {status === 'error' && (
          <>
            <svg className="w-16 h-16 mx-auto text-red-500 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
            <h2 className="text-xl font-heading text-red-600 mb-2">Verificatie mislukt</h2>
            <p className="text-gray-600 mb-4">{error}</p>
            <button
              onClick={() => router.push('/embed')}
              className="px-6 py-2 bg-[#B9965B] text-white rounded-lg hover:bg-[#A8854A]"
            >
              Opnieuw proberen
            </button>
          </>
        )}

        <p className="text-gray-400 text-xs mt-8">
          AVA Voice Assistant &middot; Beveiligde verificatie
        </p>
      </div>
    </div>
  );
}
