import Image from "next/image";

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
      <span
        className={[
          "relative shrink-0",
          compact ? "size-10" : "size-11",
        ].join(" ")}
        aria-hidden="true"
      >
        <Image
          src="/kordena-brain-mark.png"
          alt=""
          width={128}
          height={128}
          priority
          className="size-full object-contain drop-shadow-[0_0_14px_rgba(34,211,238,0.55)]"
        />
      </span>
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
