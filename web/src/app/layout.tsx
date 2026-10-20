import type { Metadata } from "next";

import { AuthSessionGuard } from "@/features/auth/components/AuthSessionGuard";
import { CommercialAccessGuard } from "@/features/commercial/components/CommercialAccessGuard";
import { UnifiedAppShell } from "@/features/shell/components/UnifiedAppShell";

import "./globals.css";

export const metadata: Metadata = {
  title: "Kordena Enterprise",
  description: "Kordena — O cérebro da sua operação.",
  icons: {
    icon: "/kordena-brain-mark-v2.png",
    apple: "/kordena-brain-mark-v2.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" className="dark" suppressHydrationWarning>
      <body>
        <AuthSessionGuard>
          <CommercialAccessGuard>
            <UnifiedAppShell>{children}</UnifiedAppShell>
          </CommercialAccessGuard>
        </AuthSessionGuard>
      </body>
    </html>
  );
}
