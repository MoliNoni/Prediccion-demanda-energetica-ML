import { useId, useState } from "react";

type InfoTipProps = {
  text: string;
  label: string;
  align?: "start" | "end";
};

/** Quiet "i" affordance: opens on hover, focus or click and closes with Escape. */
export function InfoTip({ text, label, align = "start" }: InfoTipProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="infotip" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        className="infotip-button"
        aria-label={label}
        aria-describedby={id}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
        }}
      >
        i
      </button>
      <span id={id} role="tooltip" className={`infotip-body infotip-${align}`} hidden={!open}>
        {text}
      </span>
    </span>
  );
}
