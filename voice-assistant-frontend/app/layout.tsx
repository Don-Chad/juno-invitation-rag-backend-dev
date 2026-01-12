import "@livekit/components-styles";
import "./globals.css";
import Script from "next/script";
import type { Viewport } from "next";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full min-h-[100svh]">
      <head>
        <Script id="crypto-polyfill" strategy="beforeInteractive">
          {`
            if (typeof window !== 'undefined') {
              if (!window.crypto) window.crypto = {};
              if (!window.crypto.getRandomValues) {
                window.crypto.getRandomValues = function(array) {
                  for (var i = 0; i < array.length; i++) {
                    array[i] = Math.floor(Math.random() * 256);
                  }
                  return array;
                };
              }
              if (!window.crypto.randomUUID) {
                window.crypto.randomUUID = function() {
                  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                    var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
                    return v.toString(16);
                  });
                };
              }
            }
          `}
        </Script>
      </head>
      <body className="h-full min-h-[100svh]">{children}</body>
    </html>
  );
}
