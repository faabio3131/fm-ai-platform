import * as React from "react";

import { cn } from "@/lib/utils";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      className={cn(
        "flex h-10 w-full rounded-xl border border-input bg-white/80 px-3 py-2 text-sm shadow-[inset_0_1px_rgba(255,255,255,0.5)] outline-none transition-all placeholder:text-muted-foreground focus-visible:border-blue-400 focus-visible:ring-4 focus-visible:ring-blue-500/10 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-slate-950/65 dark:shadow-none dark:focus-visible:border-blue-500/70",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
