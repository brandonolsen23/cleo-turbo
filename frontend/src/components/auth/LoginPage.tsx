import { useState } from "react";
import { Heading, TextField, Button, Callout } from "@radix-ui/themes";
import { postApi } from "../../api/client";
import type { User } from "../../hooks/useAuth";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const data = await postApi<{ token: string; user: User }>("/auth/login", { username, password });
      localStorage.setItem("cleo_token", data.token);
      localStorage.setItem("cleo_user", JSON.stringify(data.user));
      window.location.href = "/";
    } catch {
      setError("Invalid credentials");
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen" style={{ background: "var(--gray-1)" }}>
      <div className="w-[360px] rounded-[var(--card-radius)] border border-[var(--gray-6)] p-8 bg-white">
        <Heading size="5" weight="medium" className="mb-6 text-center">Cleo Turbo</Heading>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <TextField.Root
            value={username}
            onChange={(e: any) => setUsername(e.target.value)}
            placeholder="Username"
            size="3"
          />
          <TextField.Root
            value={password}
            onChange={(e: any) => setPassword(e.target.value)}
            placeholder="Password"
            type="password"
            size="3"
          />
          {error && <Callout.Root color="red" size="1"><Callout.Text>{error}</Callout.Text></Callout.Root>}
          <Button type="submit" size="3">Sign in</Button>
        </form>
      </div>
    </div>
  );
}
