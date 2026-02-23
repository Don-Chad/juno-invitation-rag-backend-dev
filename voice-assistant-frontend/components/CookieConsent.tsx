"use client";

import { useState, useEffect } from "react";

export function useStorageAccess() {
  const [hasStorageAccess, setHasStorageAccess] = useState<boolean | null>(null);
  const [isRequesting, setIsRequesting] = useState(false);

  useEffect(() => {
    // Check if we have storage access
    if (typeof document !== 'undefined' && 'hasStorageAccess' in document) {
      (document as any).hasStorageAccess().then((granted: boolean) => {
          // In Safari, even if granted is true, we might want to re-check 
          // if we are actually in an iframe and if cookies are actually working.
          setHasStorageAccess(granted);
      });
    } else {
      // Browser doesn't support Storage Access API (not Safari/modern ITP)
      setHasStorageAccess(true);
    }
  }, []);

  const requestAccess = async (): Promise<boolean> => {
    if (typeof document === 'undefined' || !('requestStorageAccess' in document)) {
      return true; // Not Safari or not supported
    }

    setIsRequesting(true);
    try {
      await (document as any).requestStorageAccess();
      setHasStorageAccess(true);
      return true;
    } catch (err) {
      console.error('Storage access denied:', err);
      setHasStorageAccess(false);
      return false;
    } finally {
      setIsRequesting(false);
    }
  };

  return { hasStorageAccess, isRequesting, requestAccess };
}

export default function CookieConsent({ onGranted }: { onGranted: () => void }) {
  const { isRequesting, requestAccess } = useStorageAccess();

  return (
    <div className="h-full flex items-center justify-center bg-white relative">
      <div className="absolute inset-0 flex items-center justify-center z-0 overflow-hidden">
        <img 
          src="/background.png" 
          alt="AVA Background" 
          className="opacity-90 w-full h-full object-cover sm:object-contain"
          style={{ imageRendering: 'crisp-edges' }}
        />
      </div>
      
      <div className="z-10 bg-white/90 backdrop-blur-md p-8 rounded-xl shadow-2xl border border-[#B9965B]/30 w-[calc(100%-2rem)] sm:w-96 text-center">
        <h2 className="text-2xl font-heading font-bold text-[#B9965B] mb-4">Enable Cookies for AVA</h2>
        <p className="text-gray-600 mb-6 font-body">
          Safari blokkeert beveiligde toegang in ingesloten vensters. Klik hieronder om toegang in te schakelen.
        </p>
        <button
          onClick={async () => {
            const granted = await requestAccess();
            if (granted) {
              onGranted();
            } else {
              // If still not granted, it might be because the user hasn't 
              // interacted with the AVA domain as a first-party yet.
              // We could show a link to open the AVA domain directly.
              const AVA_DOMAIN = process.env.NEXT_PUBLIC_AVA_DOMAIN || window.location.origin;
              window.open(AVA_DOMAIN, '_blank');
            }
          }}
          disabled={isRequesting}
          className="w-full py-3 px-6 bg-[#B9965B] hover:bg-[#A8854A] text-white rounded-lg font-body font-medium transition-all disabled:opacity-50"
        >
          {isRequesting ? 'Requesting...' : 'Enable Secure Login'}
        </button>
        <p className="mt-6 text-xs text-gray-400 font-body">
          This is required to securely identify your subscription.
        </p>
      </div>
    </div>
  );
}
