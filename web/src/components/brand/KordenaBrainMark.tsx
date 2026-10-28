import Image from "next/image";

type KordenaBrainMarkProps = {
  className?: string;
  priority?: boolean;
};

export function KordenaBrainMark({
  className = "size-10",
  priority = false,
}: KordenaBrainMarkProps) {
  return (
    <span className={`relative inline-flex shrink-0 ${className}`} aria-hidden="true">
      <Image
        src="/kordena-brain-mark-v2.png"
        alt=""
        width={128}
        height={128}
        priority={priority}
        unoptimized
        className="size-full object-contain drop-shadow-[0_0_14px_rgba(34,211,238,0.55)]"
      />
    </span>
  );
}
