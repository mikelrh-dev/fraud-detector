interface BrandShieldProps {
  className?: string;
}

/**
 * Brand mark: shield + check outline glyph. Stroke inherits `currentColor`
 * so callers tint via text-* utilities. Same geometry as the public/
 * favicon.svg source of truth (DESIGN.md — Tab identity).
 */
export function BrandShield({ className = "h-6 w-6" }: BrandShieldProps) {
  return (
    <svg
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.57-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
    </svg>
  );
}
