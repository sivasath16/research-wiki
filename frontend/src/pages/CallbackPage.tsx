import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAppStore } from "@/store/appStore";

export default function CallbackPage() {
  const navigate = useNavigate();
  const { fetchUser } = useAppStore();

  useEffect(() => {
    // The server already set the session cookie and redirected here.
    // Just re-fetch the user and go to home.
    fetchUser().then(() => navigate("/", { replace: true }));
  }, [fetchUser, navigate]);

  return (
    <div className="flex items-center justify-center min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <div className="text-center space-y-3">
        <div className="w-6 h-6 border-2 border-[#1D9E75] border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm text-zinc-500">Completing sign in...</p>
      </div>
    </div>
  );
}
