import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-semibold outline-none transition-all duration-200 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 active:translate-y-px [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-[0_10px_24px_-14px_rgba(37,99,235,0.9)] hover:-translate-y-0.5 hover:bg-blue-500 hover:shadow-[0_16px_30px_-16px_rgba(37,99,235,0.8)] active:translate-y-0",
        destructive:
          "bg-destructive text-white shadow-[0_10px_24px_-15px_rgba(220,38,38,0.8)] hover:-translate-y-0.5 hover:bg-red-500 active:translate-y-0",
        outline:
          "border border-slate-200/90 bg-white/80 text-slate-800 shadow-sm backdrop-blur hover:-translate-y-0.5 hover:border-blue-200 hover:bg-white hover:text-blue-700 hover:shadow-md dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-100 dark:hover:border-blue-500/40 dark:hover:bg-slate-800 dark:hover:text-white active:translate-y-0",
        secondary:
          "bg-secondary text-secondary-foreground shadow-sm hover:-translate-y-0.5 hover:bg-slate-200 dark:hover:bg-slate-700 active:translate-y-0",
        ghost:
          "text-foreground hover:bg-slate-900/5 hover:text-primary dark:hover:bg-white/[0.08] dark:hover:text-white",
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
