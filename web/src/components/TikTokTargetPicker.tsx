"use client";

import * as React from "react";
import { AlertTriangle, Check, Loader2, Plus, Users } from "lucide-react";
import { Button } from "./Button";
import type { TiktokAccount } from "@/lib/types";

export function TikTokTargetPicker({
  value,
  onChange,
}: {
  value: string[];
  onChange: (usernames: string[]) => void;
}) {
  const [accounts, setAccounts] = React.useState<TiktokAccount[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [adding, setAdding] = React.useState(false);
  const [newName, setNewName] = React.useState("");
  const [note, setNote] = React.useState<string | null>(null);

  async function load(selection = value) {
    setLoading(true);
    try {
      const response = await fetch("/api/tiktok/accounts");
      const data = await response.json();
      const next = (data.accounts || []) as TiktokAccount[];
      setAccounts(next);
      setNote(data.note || null);
      onChange(
        selection.filter((username) =>
          next.some((account) => account.username === username && account.ready !== false)
        )
      );
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => {
    fetch("/api/tiktok/accounts")
      .then((response) => response.json())
      .then((data) => {
        const next = (data.accounts || []) as TiktokAccount[];
        setAccounts(next);
        setNote(data.note || null);
      })
      .finally(() => setLoading(false));
    // Initial account discovery only; later refreshes are explicit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggle(username: string) {
    if (accounts.find((account) => account.username === username)?.ready === false) return;
    onChange(
      value.includes(username)
        ? value.filter((item) => item !== username)
        : [...value, username]
    );
  }

  async function add() {
    const username = newName.trim();
    if (!username) return;
    setAdding(true);
    try {
      const response = await fetch("/api/tiktok/accounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username }),
      });
      const data = await response.json();
      if (!data.ok) {
        console.error("Connexion TikTok impossible", data.error || data.stderr);
        setNote(
          "Impossible de démarrer la connexion TikTok. Vérifie la session et les journaux du serveur."
        );
        return;
      }
      setNewName("");
      const selection = [...new Set([...value, username])];
      onChange(selection);
      await load(selection);
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-medium">
          <Users className="size-4" aria-hidden="true" /> Comptes TikTok
          destinataires
        </h3>
        {accounts.length > 1 && (
          <button
            type="button"
            onClick={() =>
              onChange(
                value.length === accounts.filter((account) => account.ready !== false).length
                  ? []
                  : accounts.filter((account) => account.ready !== false).map((account) => account.username)
              )
            }
            className="text-[11px] text-cyan-300 hover:text-cyan-200"
          >
            {value.length === accounts.filter((account) => account.ready !== false).length
              ? "Tout désélectionner"
              : "Tout sélectionner"}
          </button>
        )}
      </div>

      {loading ? (
        <p
          className="flex items-center gap-2 py-2 text-sm text-ink-400"
          role="status"
        >
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />{" "}
          Chargement des comptes…
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {accounts.map((account) => {
            const selected = value.includes(account.username);
            return (
              <button
                key={account.username}
                type="button"
                onClick={() => toggle(account.username)}
                disabled={account.ready === false}
                aria-pressed={selected}
                className={`inline-flex h-10 items-center gap-1.5 rounded-full border px-3 text-sm transition ${
                  selected
                    ? "border-accent bg-accent text-white"
                    : account.ready === false
                      ? "cursor-not-allowed border-amber-400/20 text-amber-200/70"
                      : "border-white/15 text-ink-200 hover:bg-white/5"
                }`}
              >
                {selected && <Check className="size-3.5" aria-hidden="true" />}{" "}
                {account.ready === false && <AlertTriangle className="size-3.5" aria-hidden="true" />}{" "}
                @{account.username}
                {account.expired ? " · expirée" : account.ready === false ? " · reconnexion" : ""}
              </button>
            );
          })}
          {!accounts.length && (
            <p className="text-xs text-ink-400">
              Aucun compte TikTok connecté.
            </p>
          )}
        </div>
      )}

      <details className="subpanel p-3 open:bg-white/[0.035]">
        <summary className="cursor-pointer text-sm font-medium text-ink-200">
          Connecter un autre compte
        </summary>
        <div className="flex gap-2 pt-3">
          <input
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
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
            )}{" "}
            Connecter
          </Button>
        </div>
        <p className="mt-2 text-xs leading-relaxed text-ink-400">
          Les destinataires sont mémorisés pour chaque jeu. Les publications
          sont envoyées compte par compte avec un résultat distinct pour chacun.
        </p>
        {note && <p className="mt-1 text-xs text-amber-300">{note}</p>}
      </details>
    </div>
  );
}
