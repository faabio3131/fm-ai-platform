import { KordenaBrainMark } from "@/components/brand/KordenaBrainMark";

type KordenaBrandProps = {
  compact?: boolean;
  className?: string;
};

export function KordenaBrand({
  compact = false,
  className = "",
}: KordenaBrandProps) {
  return (
    <span className={`flex min-w-0 items-center gap-3 ${className}`}>
      <KordenaBrainMark
        className={compact ? "size-10" : "size-11"}
        priority
      />
      <span className="min-w-0">
        <span className="block truncate text-[15px] font-black tracking-[0.08em] text-white">
          KORDENA
        </span>
        <span
          className={[
            "text-[9px] font-bold uppercase tracking-[0.22em] text-slate-500",
            compact ? "hidden sm:block" : "block",
          ].join(" ")}
        >
          O CÉREBRO DA SUA OPERAÇÃO
        </span>
      </span>
    </span>
  );
}
