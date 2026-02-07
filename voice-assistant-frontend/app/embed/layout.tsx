import { Suspense } from "react";
import type { ReactNode } from "react";

export default function EmbedLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <div className="h-full min-h-[100svh] overflow-hidden">
      <Suspense fallback={<div className="h-full flex items-center justify-center bg-white"><div className="text-[#B9965B] font-heading text-xl">Loading...</div></div>}>
        {children}
      </Suspense>
    </div>
  );
}
