import { useEffect } from "react";
import { useAppStore } from "@/store/appStore";

export function Providers({ children }: { children: React.ReactNode }) {
  const { darkMode, fetchUser } = useAppStore();

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [darkMode]);

  return <>{children}</>;
}
