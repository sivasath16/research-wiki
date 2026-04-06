
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { fetchMe } from "@/lib/api";

interface User {
  id: number;
  github_id: number;
  login: string;
  name: string | null;
  email: string | null;
  avatar_url: string | null;
}

interface AppState {
  user: User | null;
  darkMode: boolean;
  sidebarOpen: boolean;
  fetchUser: () => Promise<void>;
  setUser: (user: User | null) => void;
  toggleDarkMode: () => void;
  toggleSidebar: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      user: null,
      darkMode: false,
      sidebarOpen: true,

      fetchUser: async () => {
        try {
          const user = await fetchMe();
          set({ user });
        } catch {
          set({ user: null });
        }
      },

      setUser: (user) => set({ user }),
      toggleDarkMode: () => set((s) => ({ darkMode: !s.darkMode })),
      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
    }),
    {
      name: "rw-app",
      partialize: (state) => ({ darkMode: state.darkMode }),
    }
  )
);
