import type { ReactNode } from "react";

import { AdminStepUpGuard } from "@/features/auth/components/AdminStepUpGuard";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return <AdminStepUpGuard>{children}</AdminStepUpGuard>;
}
