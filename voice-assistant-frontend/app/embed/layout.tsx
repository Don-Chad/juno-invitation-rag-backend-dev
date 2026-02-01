import type { ReactNode } from "react";

export default function EmbedLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <div className="h-full min-h-[100svh] overflow-hidden">
      {children}
    </div>
  );
}
