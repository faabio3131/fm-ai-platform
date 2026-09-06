import type { Metadata } from "next";

import { AuthSessionGuard } from "@/features/auth/components/AuthSessionGuard";

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
        <AuthSessionGuard>{children}</AuthSessionGuard>
      </body>
    </html>
  );
}
