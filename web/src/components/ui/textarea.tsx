import { forwardRef, TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "flex min-h-[96px] w-full rounded-xl border border-input bg-white/80 px-3 py-2.5 text-sm outline-none transition-all placeholder:text-muted-foreground focus-visible:border-blue-400 focus-visible:ring-4 focus-visible:ring-blue-500/10 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-slate-950/65 dark:text-white dark:focus-visible:border-blue-500/70",
        className,
      )}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";
