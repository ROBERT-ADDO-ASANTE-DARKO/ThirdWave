import { useEffect, useState, type RefObject } from "react";
import "./FullscreenToggle.css";

// Native Fullscreen API on the map's own wrapper element (so overlays
// like the legend stay visible) -- no plugin, no extra dependency, same
// "avoid unnecessary dependencies" choice as the rest of this app.
export function FullscreenToggle({
  targetRef,
  onToggle,
}: {
  targetRef: RefObject<HTMLElement | null>;
  onToggle?: (isFullscreen: boolean) => void;
}) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const supported = typeof document !== "undefined" && document.fullscreenEnabled;

  useEffect(() => {
    function handleChange() {
      const active = document.fullscreenElement === targetRef.current;
      setIsFullscreen(active);
      onToggle?.(active);
    }
    document.addEventListener("fullscreenchange", handleChange);
    return () => document.removeEventListener("fullscreenchange", handleChange);
  }, [targetRef, onToggle]);

  if (!supported) return null;

  function toggle() {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      targetRef.current?.requestFullscreen();
    }
  }

  return (
    <button
      type="button"
      className="fullscreen-toggle"
      onClick={toggle}
      aria-label={isFullscreen ? "Exit fullscreen" : "View fullscreen"}
      title={isFullscreen ? "Exit fullscreen" : "View fullscreen"}
    >
      {isFullscreen ? (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M9 4V8H5M15 4V8H19M9 20V16H5M15 20V16H19"
            stroke="#1E4E6B"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      ) : (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M4 9V5H8M16 5H20V9M20 15V19H16M8 19H4V15"
            stroke="#1E4E6B"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      )}
    </button>
  );
}
