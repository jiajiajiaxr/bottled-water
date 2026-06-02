import { useLocation, useNavigate, Navigate } from "react-router-dom";
import { LoginScreen } from "@/features/auth/components/LoginScreen";
import type { User } from "@/types";

interface LoginRouteProps {
  user?: User;
  onLogin: (user: User) => void;
}

export function LoginRoute({ user, onLogin }: LoginRouteProps) {
  const navigate = useNavigate();
  const location = useLocation();

  if (user) return <Navigate to="/app" replace />;

  return (
    <LoginScreen
      onLogin={(nextUser) => {
        onLogin(nextUser);
        const from = (
          location.state as {
            from?: { pathname?: string; search?: string };
          } | null
        )?.from;
        const target =
          from?.pathname && from.pathname !== "/login"
            ? `${from.pathname}${from.search ?? ""}`
            : "/app";
        navigate(target, { replace: true });
      }}
    />
  );
}
