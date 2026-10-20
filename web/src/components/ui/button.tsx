import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-semibold outline-none transition-all duration-200 focus-visible:ring-2 focus-visible:ring-ring/80 focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-45 active:translate-y-px [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "border border-blue-300/10 bg-[linear-gradient(135deg,#2f7cf6,#078bd4_58%,#0ea5e9)] text-white shadow-[0_16px_34px_-18px_rgba(47,124,246,0.92)] hover:-translate-y-0.5 hover:brightness-110 hover:shadow-[0_20px_38px_-18px_rgba(47,124,246,0.8)] active:translate-y-0",
        destructive:
          "bg-destructive text-white shadow-[0_10px_24px_-15px_rgba(220,38,38,0.8)] hover:-translate-y-0.5 hover:bg-red-500 active:translate-y-0",
        outline:
          "border border-slate-600/70 bg-slate-950/45 text-slate-100 shadow-[inset_0_1px_rgba(255,255,255,0.035)] backdrop-blur hover:-translate-y-0.5 hover:border-sky-400/35 hover:bg-slate-800/80 hover:text-white hover:shadow-[0_14px_32px_-24px_rgba(56,189,248,0.65)] active:translate-y-0",
        secondary:
          "border border-slate-600/40 bg-secondary text-secondary-foreground shadow-sm hover:-translate-y-0.5 hover:bg-slate-700 active:translate-y-0",
        ghost:
          "text-slate-300 hover:bg-white/[0.065] hover:text-white",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-lg px-3 text-xs",
        lg: "h-12 rounded-xl px-6 text-sm",
        icon: "size-10 rounded-xl",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}

export { Button, buttonVariants };
