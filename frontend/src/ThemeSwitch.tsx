import { Moon, Sun } from 'lucide-react';

export type Theme = 'dark' | 'light';

const themeKey = 'ai-navigator.theme';

export function readTheme(): Theme {
  try {
    return localStorage.getItem(themeKey) === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

export function saveTheme(theme: Theme) {
  try {
    localStorage.setItem(themeKey, theme);
  } catch {
    // The switch still works when the browser blocks storage.
  }
}

// Adapted from Watermelon UI Switch 10 to the terminal's CSS and icons.
export function ThemeSwitch({ theme, onChange }: { theme: Theme; onChange: (theme: Theme) => void }) {
  const light = theme === 'light';

  return (
    <button className="theme-switch" type="button" role="switch" aria-checked={light}
      aria-label="Светлая тема" title={light ? 'Включить тёмную тему' : 'Включить светлую тему'}
      onClick={() => onChange(light ? 'dark' : 'light')}>
      <span className="theme-switch-thumb" aria-hidden="true" />
      <Moon className="theme-switch-moon" size={20} aria-hidden="true" />
      <Sun className="theme-switch-sun" size={20} aria-hidden="true" />
    </button>
  );
}
