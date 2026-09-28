import { MessageCircle, Phone } from "lucide-react";

export function WhatsAppChannelMark({
  className = "size-6",
}: {
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={`relative inline-flex shrink-0 items-center justify-center rounded-full bg-emerald-400/[0.12] text-emerald-200 ring-1 ring-emerald-300/25 shadow-[0_0_18px_-7px_rgba(52,211,153,0.95)] ${className}`}
    >
      <MessageCircle
        className="absolute size-[82%] fill-emerald-400/[0.08] text-emerald-300"
        strokeWidth={2}
      />
      <Phone className="relative size-[38%] text-emerald-100" strokeWidth={2.5} />
    </span>
  );
}
