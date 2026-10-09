export function Logo() {
  return (
    <div className="flex items-center gap-3">
      <svg viewBox="0 0 48 44" className="size-9 text-primary" fill="none" aria-hidden="true">
        <path d="M3 38 21 5l9 17 5-9 10 25H3Z" stroke="currentColor" strokeWidth="2.3" />
        <path d="m14 19 7 5 7-6M8 38l13-14 13 14" stroke="currentColor" strokeWidth="1.5" />
      </svg>
      <span className="text-xl font-semibold tracking-tight">
        AscentIQ
        <span className="block text-[9px] font-normal tracking-widest text-muted-foreground">
          SAÚDE E FITNESS PESSOAL
        </span>
      </span>
    </div>
  );
}
