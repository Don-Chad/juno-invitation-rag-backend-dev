"use client";

import { useEffect, useState, Suspense } from "react";
import { isSignInWithEmailLink, signInWithEmailLink } from "firebase/auth";
import { auth } from "@/lib/firebase";
import { useRouter, useSearchParams } from "next/navigation";

function FinishSignUpContent() {
  const [status, setStatus] = useState<'verifying' | 'success' | 'error'>('verifying');
  const [error, setError] = useState<string>('');
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    async function completeSignIn() {
      // Check if this is a sign-in link
      if (!isSignInWithEmailLink(auth, window.location.href)) {
        setStatus('error');
        setError('Invalid or expired link. Please request a new magic link.');
        return;
      }

      // Get email from localStorage
      let email = window.localStorage.getItem('emailForSignIn');

      // If missing (user switched devices), ask for it
      if (!email) {
        email = window.prompt('Please provide your email for confirmation') || '';
      }

      if (!email) {
        setStatus('error');
        setError('Email is required to complete sign-in');
        return;
      }

      try {
        // Complete sign-in
        await signInWithEmailLink(auth, email, window.location.href);
        
        // Clear email from storage
        window.localStorage.removeItem('emailForSignIn');
        
        // Get site_id from URL to redirect back properly
        const siteId = searchParams.get('site_id');
        
        setStatus('success');
        
        // Redirect back to embed page after short delay
        setTimeout(() => {
          const redirectUrl = siteId 
            ? `/embed?site_id=${siteId}`
            : '/embed';
          router.push(redirectUrl);
        }, 1500);
        
      } catch (err: any) {
        console.error('Sign-in error:', err);
        setStatus('error');
        setError(err.message || 'Failed to complete sign-in. The link may have expired.');
      }
    }

    completeSignIn();
  }, [router, searchParams]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-white relative">
      <div className="absolute inset-0 flex items-center justify-center z-0 overflow-hidden">
        <img 
          src="/background.png" 
          alt="AVA Background" 
          className="opacity-90 w-full h-full object-cover sm:object-contain"
          style={{ imageRendering: 'crisp-edges' }}
        />
      </div>

      <div className="z-10 bg-white/90 backdrop-blur-md p-8 rounded-xl shadow-2xl border border-[#B9965B]/30 w-[calc(100%-2rem)] sm:w-96 text-center">
        {status === 'verifying' && (
          <>
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#B9965B] mx-auto mb-4"></div>
            <h2 className="text-xl font-heading text-[#B9965B]">Verifying your device...</h2>
          </>
        )}
        
        {status === 'success' && (
          <>
            <svg className="w-16 h-16 mx-auto text-green-500 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <h2 className="text-xl font-heading text-[#B9965B] mb-2">Device Verified!</h2>
            <p className="text-gray-600">Redirecting you to AVA...</p>
          </>
        )}
        
        {status === 'error' && (
          <>
            <svg className="w-16 h-16 mx-auto text-red-500 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
            <h2 className="text-xl font-heading text-red-600 mb-2">Verification Failed</h2>
            <p className="text-gray-600 mb-4">{error}</p>
            <button
              onClick={() => window.location.href = '/embed'}
              className="px-6 py-2 bg-[#B9965B] text-white rounded-lg hover:bg-[#A8854A]"
            >
              Try Again
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function FinishSignUpPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-white">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#B9965B]"></div>
      </div>
    }>
      <FinishSignUpContent />
    </Suspense>
  );
}
