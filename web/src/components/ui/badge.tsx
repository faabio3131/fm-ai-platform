import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex w-fit items-center justify-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold leading-none whitespace-nowrap backdrop-blur",
  {
    variants: {
      variant: {
        default: "border-blue-300/10 bg-blue-500/16 text-blue-200 shadow-[0_8px_20px_-14px_rgba(47,124,246,0.9)]",
        secondary: "border-slate-500/20 bg-slate-700/55 text-slate-200",
        destructive: "border-red-400/15 bg-red-500/18 text-red-100",
        outline: "border-slate-600/70 bg-slate-950/42 text-slate-200",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

function Badge({ className, variant, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
