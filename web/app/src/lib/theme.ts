import { useEffect, useState } from "react";

/** Light is the default; the .dark class is the runtime switch, persisted. */
export function useTheme() {
  const [dark, setDark] = useState(
    () => document.documentElement.classList.contains("dark"),
  );
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("prosodi-theme", dark ? "dark" : "light");
    } catch {
      /* private mode, ignore */
    }
  }, [dark]);
  return { dark, toggle: () => setDark((d) => !d) };
}

/** Read a CSS custom property off the document root (for the waveform colours). */
export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
