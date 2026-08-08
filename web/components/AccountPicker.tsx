"use client";

import * as React from "react";
import { Loader2, Plus, User } from "lucide-react";
import { Button } from "./Button";
import type { TiktokAccount } from "@/lib/types";

export function AccountPicker({
  value,
  onChange,
}: {
  value?: string;
  onChange: (username: string | undefined) => void;
}) {
  const [accounts, setAccounts] = React.useState<TiktokAccount[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [adding, setAdding] = React.useState(false);
  const [newName, setNewName] = React.useState("");
  const [note, setNote] = React.useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const r = await fetch("/api/tiktok/accounts");
      const j = await r.json();
      setAccounts(j.accounts || []);
      setNote(j.note || null);
      if (!value && j.accounts?.[0]) onChange(j.accounts[0].username);
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function add() {
    const username = newName.trim();
    if (!username) return;
    setAdding(true);
    try {
      const r = await fetch("/api/tiktok/accounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username }),
      });
      const j = await r.json();
      if (!j.ok) {
        console.error("Connexion TikTok impossible", j.error || j.stderr);
        alert(
          "Impossible de connecter ce compte TikTok. Vérifie la session et les journaux du serveur."
        );
      } else {
        setNewName("");
        onChange(username);
        await load();
      }
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium flex items-center gap-2">
          <User className="size-4" aria-hidden="true" /> Compte TikTok
        </h3>
      </div>

      {loading ? (
        <div
          className="flex items-center gap-2 py-2 text-sm text-ink-400"
          role="status"
        >
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />{" "}
          Chargement des comptes…
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {accounts.map((a) => (
              <button
                key={a.username}
                type="button"
                onClick={() => onChange(a.username)}
                aria-pressed={value === a.username}
                className={`h-10 rounded-full border px-3 text-sm transition ${
                  value === a.username
                    ? "bg-accent text-white border-accent"
                    : "border-white/15 text-ink-200 hover:bg-white/5"
                }`}
              >
                @{a.username}
              </button>
            ))}
            {accounts.length === 0 && (
              <p className="text-xs text-ink-400">Aucun compte connecté.</p>
            )}
          </div>

          <details className="subpanel p-3 open:bg-white/[0.035]">
            <summary className="cursor-pointer text-sm font-medium text-ink-200">
              Connecter un compte
            </summary>
            <div className="flex gap-2 pt-3">
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Nom d’utilisateur TikTok"
                aria-label="Nom d’utilisateur TikTok"
                className="field-control h-11 min-w-0 flex-1"
              />
              <Button
                type="button"
                onClick={add}
                disabled={adding || !newName.trim()}
              >
                {adding ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Plus className="size-4" aria-hidden="true" />
                )}
                Connecter
              </Button>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-ink-400">
              La connexion s’ouvre une seule fois dans Chrome. Après
              identification manuelle, la session est conservée pour les
              prochaines publications.
            </p>
            {note && <p className="mt-1 text-xs text-amber-300">{note}</p>}
          </details>
        </>
      )}
    </div>
  );
}
