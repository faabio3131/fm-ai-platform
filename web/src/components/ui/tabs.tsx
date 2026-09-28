"use client";

import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";

import { cn } from "@/lib/utils";

const Tabs = TabsPrimitive.Root;

function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn("inline-flex min-h-10 items-center justify-center rounded-xl border border-slate-700/65 bg-slate-950/42 p-1 text-slate-400 shadow-[inset_0_1px_rgba(255,255,255,0.025)]", className)} {...props} />;
}

function TabsTrigger({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return <TabsPrimitive.Trigger className={cn("inline-flex min-h-8 items-center justify-center whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-semibold outline-none transition-all focus-visible:ring-2 focus-visible:ring-ring data-[state=active]:bg-[linear-gradient(135deg,rgba(47,124,246,0.22),rgba(14,165,233,0.14))] data-[state=active]:text-white data-[state=active]:shadow-[inset_0_0_0_1px_rgba(96,165,250,0.16)]", className)} {...props} />;
}

function TabsContent({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content className={cn("mt-3 outline-none focus-visible:ring-2 focus-visible:ring-ring", className)} {...props} />;
}

export { Tabs, TabsContent, TabsList, TabsTrigger };
