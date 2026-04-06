import { Routes, Route } from "react-router-dom";
import HomePage from "@/pages/HomePage";
import WikiPage from "@/pages/WikiPage";
import CallbackPage from "@/pages/CallbackPage";
import { ProtectedRoute } from "@/components/ProtectedRoute";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/auth/callback" element={<CallbackPage />} />
      <Route
        path="/wiki/:repoId"
        element={
          <ProtectedRoute>
            <WikiPage />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}
