import type { CSSProperties } from "react";

type SkeletonProps = {
  variant?: "block" | "line";
  width?: string | number;
  height?: string | number;
  className?: string;
};

/** Decorative placeholder; the loading region that hosts it carries aria-busy. */
export function Skeleton({ variant = "line", width, height, className = "" }: SkeletonProps) {
  const style: CSSProperties = { width, height };
  return <span aria-hidden="true" className={`skeleton skeleton-${variant} ${className}`.trim()} style={style} />;
}

export function SkeletonRows({ rows, columns }: { rows: number; columns: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, row) => (
        <tr key={row} className="skeleton-row">
          {Array.from({ length: columns }, (_, column) => (
            <td key={column}>
              <Skeleton width={column === 0 ? 84 : "70%"} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
