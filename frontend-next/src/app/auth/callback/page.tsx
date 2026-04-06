"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAppStore } from "@/store/appStore";

export default function CallbackPage() {
  const router = useRouter();
  const { fetchUser } = useAppStore();

  useEffect(() => {
    fetchUser().then(() => router.replace("/"));
  }, [fetchUser, router]);

  return (
    <div className="flex items-center justify-center min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <div className="text-center space-y-3">
        <div className="w-6 h-6 border-2 border-[#1D9E75] border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm text-zinc-500">Completing sign in...</p>
      </div>
    </div>
  );
}
