import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Theme = "dark" | "light";

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (t: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

// Chỉ lưu khi người dùng tự chọn. Khoá cũ "stcs.theme" bị bỏ qua vì phiên bản trước tự ghi "dark"
// ngay lần mở đầu tiên, không phân biệt được với lựa chọn thật.
const STORAGE_KEY = "stcs.theme.choice";

function readSaved(): Theme | null {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved === "dark" || saved === "light" ? saved : null;
  } catch {
    return null;
  }
}

function saveChoice(t: Theme) {
  try {
    localStorage.setItem(STORAGE_KEY, t);
  } catch {
    /* trình duyệt chặn lưu trữ — vẫn đổi theme trong phiên */
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Mặc định giao diện sáng; giữ lựa chọn tối/sáng nếu người dùng đã tự đổi
  const [theme, setThemeState] = useState<Theme>(() => readSaved() ?? "light");

  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute("data-theme", theme);
    if (theme === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }

    // Cập nhật thẻ meta theme-color của trình duyệt
    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    if (metaThemeColor) {
      metaThemeColor.setAttribute("content", theme === "dark" ? "#0A0F1A" : "#F4F6FA");
    }
  }, [theme]);

  const toggleTheme = () => {
    setThemeState((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      saveChoice(next);
      return next;
    });
  };

  const setTheme = (t: Theme) => {
    saveChoice(t);
    setThemeState(t);
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme phải được sử dụng bên trong ThemeProvider");
  }
  return ctx;
}
