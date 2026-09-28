import * as React from "react";

import { cn } from "@/lib/utils";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      className={cn(
        "flex h-10 w-full rounded-xl border border-input bg-slate-950/52 px-3 py-2 text-sm text-slate-100 shadow-[inset_0_1px_rgba(255,255,255,0.035)] outline-none transition-all placeholder:text-slate-500 focus-visible:border-sky-400/70 focus-visible:ring-4 focus-visible:ring-sky-500/10 disabled:cursor-not-allowed disabled:opacity-45",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
