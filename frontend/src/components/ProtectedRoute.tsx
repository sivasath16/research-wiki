import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAppStore } from "@/store/appStore";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, fetchUser } = useAppStore();
  const [checked, setChecked] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    fetchUser().finally(() => setChecked(true));
  }, [fetchUser]);

  useEffect(() => {
    if (checked && !user) {
      navigate("/", { replace: true });
    }
  }, [checked, user, navigate]);

  if (!checked) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-50 dark:bg-zinc-950">
        <div className="w-6 h-6 border-2 border-[#1D9E75] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return <>{children}</>;
}
