import type { Metadata } from "next";

import { AuthSessionGuard } from "@/features/auth/components/AuthSessionGuard";
import { UnifiedAppShell } from "@/features/shell/components/UnifiedAppShell";

import "./globals.css";

export const metadata: Metadata = {
  title: "Kordena Enterprise",
  description: "Kordena enterprise operations workspace",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body>
        <AuthSessionGuard>
          <UnifiedAppShell>{children}</UnifiedAppShell>
        </AuthSessionGuard>
      </body>
    </html>
  );
}
