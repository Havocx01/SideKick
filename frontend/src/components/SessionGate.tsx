import { createContext, useContext, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { LockKeyhole } from "lucide-react";
import { ApiError, invalidateSessionRequests, request, SESSION_EXPIRED_EVENT } from "../api/client";
import { Button } from "./Chrome";
import { ThemeToggle } from "./ThemeToggle";
import styles from "./session-gate.module.css";

interface SessionInfo {
  required: boolean;
  authenticated: boolean;
  owner: string | null;
  budgets: { calls: number; completionTokens: number; searches: number; mutations: number } | null;
}

interface SessionActions {
  session: SessionInfo;
  busy: boolean;
  error: string;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionActions | null>(null);
const SESSION_CHANGE = "sidekick-session-change";

function message(error: unknown) {
  return error instanceof ApiError && error.detail ? error.detail : "Could not reach the workspace. Try again.";
}

export function SessionGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [bootError, setBootError] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const version = useRef(0);
  const hosted = useRef(false);

  useEffect(() => {
    const current = ++version.current;
    let active = true;
    async function load() {
      try {
        const health = await request<{ requires_sign_in?: boolean }>("/api/health");
        if (!active || current !== version.current) return;
        hosted.current = health.requires_sign_in === true;
        const next = hosted.current ? await request<SessionInfo>("/api/session") : { required: false, authenticated: true, owner: null, budgets: null };
        if (active && current === version.current) setSession(next);
      } catch (error) {
        if (active && current === version.current) setBootError(message(error));
      }
    }
    void load();
    return () => { active = false; };
  }, [attempt]);

  useEffect(() => {
    const expired = () => {
      if (!hosted.current) return;
      invalidateSessionRequests();
      version.current++;
      setSession({ required: true, authenticated: false, owner: null, budgets: null });
      setPassword("");
      setBusy(false);
      setError("");
      setNotice("Your session ended. Sign in again to continue.");
    };
    const changed = (event: StorageEvent) => {
      if (event.key !== SESSION_CHANGE || !hosted.current) return;
      invalidateSessionRequests();
      version.current++;
      setSession(null);
      setBootError("");
      setPassword("");
      setBusy(false);
      setError("");
      setAttempt(value => value + 1);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, expired);
    window.addEventListener("storage", changed);
    return () => { window.removeEventListener(SESSION_EXPIRED_EVENT, expired); window.removeEventListener("storage", changed); };
  }, []);

  function broadcast() {
    try {
      localStorage.setItem(SESSION_CHANGE, `${Date.now()}-${Math.random()}`);
    } catch (error) {
      console.warn("Could not notify other tabs of the session change.", error);
    }
  }

  async function signIn(event: FormEvent) {
    event.preventDefault();
    invalidateSessionRequests();
    const current = ++version.current;
    setBusy(true);
    setError("");
    try {
      const next = await request<SessionInfo>("/api/session/login", { method: "POST", body: JSON.stringify({ username, password }) });
      if (current !== version.current) return;
      if (!next.authenticated) throw new Error("Sign in was not completed.");
      invalidateSessionRequests();
      setSession(next);
      setNotice("");
      broadcast();
    } catch (error) {
      if (current === version.current) setError(message(error));
    } finally {
      if (current === version.current) { setPassword(""); setBusy(false); }
    }
  }

  async function signOut() {
    invalidateSessionRequests();
    const current = ++version.current;
    setBusy(true);
    setError("");
    try {
      const next = await request<SessionInfo>("/api/session/logout", { method: "POST" });
      if (current !== version.current) return;
      invalidateSessionRequests();
      setSession(next);
      setUsername("");
      setNotice("");
      broadcast();
    } catch (error) {
      if (current === version.current) setError(message(error));
    } finally {
      if (current === version.current) { setPassword(""); setBusy(false); }
    }
  }

  if (session?.authenticated) {
    return <SessionContext.Provider value={session.required ? { session, busy, error, signOut } : null}>{children}</SessionContext.Provider>;
  }

  return (
    <main className={styles.page}>
      <div className={styles.frame}>
        <header className={styles.header}><div className="brand-mark">Side<span>kick</span></div><ThemeToggle /></header>
        <section className={styles.card} aria-labelledby="session-title">
          <div className={styles.lock}><LockKeyhole size={22} strokeWidth={1.7} aria-hidden="true" /></div>
          <p className={styles.eyebrow}>Private workspace</p>
          <h1 id="session-title">{session ? "Sign in to your workspace" : "Connect to your workspace"}</h1>
          {session ? <>
            <p className={styles.description}>Access your datasets, investigations and saved results.</p>
            {notice && <p className={styles.notice} role="status">{notice}</p>}
            <form className={styles.form} onSubmit={signIn} aria-busy={busy}>
              <label htmlFor="session-username">Username<input id="session-username" name="username" autoComplete="username" maxLength={64} value={username} onChange={event => setUsername(event.target.value)} required disabled={busy} /></label>
              <label htmlFor="session-password">Password<input id="session-password" name="password" type="password" autoComplete="current-password" maxLength={1024} value={password} onChange={event => setPassword(event.target.value)} required disabled={busy} /></label>
              {error && <p className={styles.error} role="alert">{error}</p>}
              <Button type="submit" variant="primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
            </form>
            <p className={styles.footnote}>Use the credentials configured for this workspace.</p>
          </> : bootError ? <>
            <p className={styles.error} role="alert">{bootError}</p>
            <Button onClick={() => { setBootError(""); setAttempt(value => value + 1); }}>Retry connection</Button>
          </> : <p className={styles.description} role="status">Checking workspace access…</p>}
        </section>
      </div>
    </main>
  );
}

export function SessionControls() {
  const actions = useContext(SessionContext);
  if (!actions) return null;
  const { session, busy, error, signOut } = actions;
  return <div className={styles.controls}>
    <span className={styles.owner} title={`Signed in as ${session.owner}`}>{session.owner}</span>
    <Button variant="ghost" onClick={() => void signOut()} disabled={busy} aria-label="Sign out">{busy ? "Signing out…" : "Sign out"}</Button>
    {error && <p className={styles.logoutError} role="alert">{error}</p>}
  </div>;
}

export function useWorkspaceSession() {
  return useContext(SessionContext)?.session ?? null;
}
