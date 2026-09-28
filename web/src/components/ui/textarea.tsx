import { forwardRef, TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "flex min-h-[96px] w-full rounded-xl border border-input bg-slate-950/52 px-3 py-2.5 text-sm text-slate-100 shadow-[inset_0_1px_rgba(255,255,255,0.035)] outline-none transition-all placeholder:text-slate-500 focus-visible:border-sky-400/70 focus-visible:ring-4 focus-visible:ring-sky-500/10 disabled:cursor-not-allowed disabled:opacity-45",
        className,
      )}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";
