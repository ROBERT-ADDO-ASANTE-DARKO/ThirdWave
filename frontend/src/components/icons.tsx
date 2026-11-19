import type { NavIconKey } from "../nav";

// Same inline-stroke SVGs used in the Design-canvas mockup (Main.dc.html /
// Planning.dc.html), carried over 1:1 for visual continuity. `color`
// defaults to the sidebar's dim icon tone; pass "currentColor" to let the
// active nav row's text color take over.
interface IconProps {
  color?: string;
  size?: number;
}

const base = (color = "#9FB2C2", size = 17) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none" as const,
  "aria-hidden": true,
  stroke: color,
  strokeWidth: 1.7,
});

export function NavIcon({ icon, color, size }: IconProps & { icon: NavIconKey }) {
  const p = base(color, size);
  switch (icon) {
    case "overview":
      return (
        <svg {...p} strokeWidth={1.8}>
          <rect x="3" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="3" width="7" height="7" rx="1.5" />
          <rect x="3" y="14" width="7" height="7" rx="1.5" />
          <rect x="14" y="14" width="7" height="7" rx="1.5" />
        </svg>
      );
    case "map":
      return (
        <svg {...p}>
          <path d="M12 21C12 21 19 15.6 19 10.2C19 6.22 15.87 3 12 3C8.13 3 5 6.22 5 10.2C5 15.6 12 21 12 21Z" />
          <circle cx="12" cy="10" r="2.4" />
        </svg>
      );
    case "queue":
      return (
        <svg {...p}>
          <rect x="3.5" y="4" width="17" height="16" rx="2" />
          <path d="M3.5 9H20.5" />
          <path d="M8 13H16" strokeLinecap="round" />
        </svg>
      );
    case "verification":
      return (
        <svg {...p}>
          <path d="M12 3L19 6V11C19 16 16 19.5 12 21C8 19.5 5 16 5 11V6L12 3Z" />
          <path d="M9 12L11.3 14.3L15.5 10" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "allocation":
      return (
        <svg {...p}>
          <circle cx="12" cy="12" r="8.5" />
          <path d="M12 7V12L15.3 14" strokeLinecap="round" />
        </svg>
      );
    case "closures":
      return (
        <svg {...p}>
          <path d="M4 18L9 7H15L20 18" strokeLinejoin="round" />
          <path d="M6.5 13H17.5" />
        </svg>
      );
    case "timeline":
      return (
        <svg {...p}>
          <circle cx="12" cy="12" r="8.5" />
          <path d="M12 7.5V12L15 13.6" strokeLinecap="round" />
        </svg>
      );
    case "analytics":
      return (
        <svg {...p} strokeWidth={1.9}>
          <path d="M4 20V10M11 20V4M18 20V13" strokeLinecap="round" />
        </svg>
      );
    case "briefing":
      return (
        <svg {...p}>
          <path d="M6 3.5H16L19 7V20.5H6V3.5Z" strokeLinejoin="round" />
          <path d="M9 11H15M9 15H15" strokeLinecap="round" />
        </svg>
      );
    case "vulnerability":
      return (
        <svg {...p}>
          <path d="M12 2.5C12 2.5 5 11 5 15.5C5 19.09 8.13 22 12 22C15.87 22 19 19.09 19 15.5C19 11 12 2.5 12 2.5Z" strokeLinejoin="round" />
        </svg>
      );
    case "trend":
      return (
        <svg {...p}>
          <path d="M4 17L9.5 11L13.5 14.5L20 7" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M14.5 7H20V12.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "drain":
      return (
        <svg {...p}>
          <circle cx="12" cy="12" r="8.5" />
          <path d="M8.5 9.5H15.5M8.5 12H15.5M8.5 14.5H13" strokeLinecap="round" />
        </svg>
      );
    case "exposure":
      return (
        <svg {...p}>
          <circle cx="9" cy="8" r="2.6" />
          <path d="M3.5 19C3.5 15.5 6 13.2 9 13.2C12 13.2 14.5 15.5 14.5 19" strokeLinecap="round" />
          <circle cx="17" cy="9.5" r="2.1" />
          <path d="M14.8 13.4C17.3 13.5 19.5 15.3 19.8 18.2" strokeLinecap="round" />
        </svg>
      );
    case "scenario":
      return (
        <svg {...p}>
          <rect x="3.5" y="4.5" width="8" height="15" rx="1.5" />
          <rect x="13" y="4.5" width="8" height="15" rx="1.5" strokeDasharray="2.5 2.5" />
        </svg>
      );
    case "pluvial":
      return (
        <svg {...p}>
          <path d="M4 15C5 13 7 13 8 15C9 17 11 17 12 15C13 13 15 13 16 15C17 17 19 17 20 15" strokeLinecap="round" />
          <path d="M4 19C5 17 7 17 8 19C9 21 11 21 12 19C13 17 15 17 16 19C17 21 19 21 20 19" strokeLinecap="round" />
        </svg>
      );
    case "flood3d":
      return (
        <svg {...p}>
          <path d="M3 9L12 4.5L21 9L12 13.5L3 9Z" strokeLinejoin="round" />
          <path d="M3 14L12 18.5L21 14" strokeLinejoin="round" />
        </svg>
      );
    case "assistant":
      return (
        <svg {...p}>
          <path d="M12 3.5C7 3.5 4 6.8 4 10.5C4 13 5.3 15.1 7.4 16.4L6.7 20L10.8 17.7C11.2 17.7 11.6 17.7 12 17.7C17 17.7 20 14.4 20 10.6C20 6.8 17 3.5 12 3.5Z" strokeLinejoin="round" />
        </svg>
      );
    default:
      return null;
  }
}

export function LogoMark({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 2.5C12 2.5 5 11 5 15.5C5 19.09 8.13 22 12 22C15.87 22 19 19.09 19 15.5C19 11 12 2.5 12 2.5Z"
        stroke="#FFFFFF"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function SearchIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="11" cy="11" r="7" stroke="#8B98A5" strokeWidth="1.8" />
      <path d="M20 20L16.5 16.5" stroke="#8B98A5" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function BellIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M6 10.5C6 7 8.7 4.5 12 4.5C15.3 4.5 18 7 18 10.5V14L20 17H4L6 14V10.5Z"
        stroke="#1E4E6B"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
      <path d="M9.5 19.5C9.5 20.6 10.6 21.5 12 21.5C13.4 21.5 14.5 20.6 14.5 19.5" stroke="#1E4E6B" strokeWidth="1.7" />
    </svg>
  );
}
