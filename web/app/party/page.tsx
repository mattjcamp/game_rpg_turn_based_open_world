"use client";

/**
 * Form Party — pick which up-to-four roster members make up the
 * adventuring party. Mirrors the title-screen "FORM PARTY" flow in
 * `src/game.py` (`_title_form_party`, `_handle_form_party_input`).
 *
 * Loaded from localStorage if the player has already edited; otherwise
 * seeded from the bundled `data/party.json`. Saving writes back to
 * localStorage so subsequent runs (Enter the World, Combat-only) see
 * the chosen roster.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  loadParty,
  saveStoredRoster,
  clearStoredRoster,
  _clearPartyCache,
  type Party,
  type PartyMember,
} from "@/game/world/Party";
import { dataPath } from "@/game/world/Module";

const MAX_ACTIVE = 4;

function statMod(value: number): number {
  return Math.floor((value - 10) / 2);
}

function fmtMod(n: number): string {
  return n >= 0 ? `+${n}` : String(n);
}

export default function FormPartyPage() {
  const [party, setParty] = useState<Party | null>(null);
  const [active, setActive] = useState<Set<number>>(new Set());
  const [message, setMessage] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    // Force a reload — the formation page might've been opened after a
    // create-character round-trip, so we drop the in-memory cache and
    // re-read from localStorage / disk.
    _clearPartyCache();
    loadParty(dataPath("party.json")).then((p) => {
      if (!alive) return;
      setParty(p);
      setActive(new Set(p.activeParty.filter((i) => i < p.roster.length)));
    });
    return () => { alive = false; };
  }, []);

  function toggle(idx: number): void {
    if (!party) return;
    const next = new Set(active);
    if (next.has(idx)) {
      next.delete(idx);
    } else {
      if (next.size >= MAX_ACTIVE) {
        setMessage(`Party is full (max ${MAX_ACTIVE}).`);
        return;
      }
      next.add(idx);
    }
    setActive(next);
    setMessage(null);
  }

  function save(): void {
    if (!party) return;
    if (active.size === 0) {
      setMessage("Select at least one character.");
      return;
    }
    party.activeParty = Array.from(active).sort((a, b) => a - b);
    saveStoredRoster(party);
    setMessage("Party saved!");
  }

  function deleteMember(idx: number): void {
    if (!party) return;
    const next: Party = {
      ...party,
      roster: party.roster.filter((_, i) => i !== idx),
      // Renumber active indices around the removal.
      activeParty: party.activeParty
        .filter((i) => i !== idx)
        .map((i) => (i > idx ? i - 1 : i)),
    };
    setParty(next);
    const newActive = new Set<number>();
    for (const i of active) {
      if (i === idx) continue;
      newActive.add(i > idx ? i - 1 : i);
    }
    setActive(newActive);
    saveStoredRoster(next);
    setConfirmDelete(null);
    setMessage(`${party.roster[idx].name} removed from roster.`);
  }

  function resetRoster(): void {
    if (!confirm("Discard local roster edits and reload data/party.json?")) return;
    clearStoredRoster();
    _clearPartyCache();
    loadParty(dataPath("party.json")).then((p) => {
      setParty(p);
      setActive(new Set(p.activeParty));
      setMessage("Roster reset to bundled defaults.");
    });
  }

  if (!party) {
    return (
      <main className="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center px-6">
        <p className="text-parchment/60">Loading roster&hellip;</p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col px-6 py-8">
      <div className="mb-4 flex items-center justify-between">
        <Link href="/" className="text-sm text-parchment/60 hover:text-parchment">
          &larr; Title
        </Link>
        <h1 className="font-display text-3xl text-parchment">Form Party</h1>
        <span className="w-16" />
      </div>

      <p className="text-sm text-parchment/70">
        Select up to {MAX_ACTIVE} adventurers from the roster. The chosen
        party comes with you when you Enter the World.
      </p>

      <div className="mt-2 text-xs text-parchment/50">
        Active: <span className="text-ember">{active.size}</span> / {MAX_ACTIVE}
      </div>

      {message && (
        <div className="mt-3 rounded border border-ember/40 bg-ember/10 px-3 py-2 text-sm text-parchment">
          {message}
        </div>
      )}

      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {party.roster.map((m, idx) => (
          <RosterCard
            key={`${m.name}-${idx}`}
            member={m}
            selected={active.has(idx)}
            onToggle={() => toggle(idx)}
            onDelete={() => setConfirmDelete(idx)}
          />
        ))}
        {party.roster.length === 0 && (
          <div className="col-span-full rounded border border-parchment/20 bg-parchment/5 p-6 text-center text-sm text-parchment/60">
            No characters in the roster yet. Click <em>Create Character</em>
            below to add one.
          </div>
        )}
      </div>

      {confirmDelete !== null && (
        <div className="mt-4 flex items-center justify-between rounded border border-red-500/40 bg-red-500/10 px-4 py-3">
          <span className="text-sm text-parchment">
            Permanently delete <strong>{party.roster[confirmDelete].name}</strong>?
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => deleteMember(confirmDelete)}
              className="rounded bg-red-500/30 px-3 py-1 text-sm text-parchment hover:bg-red-500/50"
            >
              Delete
            </button>
            <button
              onClick={() => setConfirmDelete(null)}
              className="rounded border border-parchment/30 px-3 py-1 text-sm text-parchment/80 hover:bg-parchment/10"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-2">
          <Link
            href="/party/new"
            className="rounded border border-ember bg-ember/20 px-4 py-2 text-sm text-parchment hover:bg-ember/40"
          >
            Create Character
          </Link>
          <button
            onClick={resetRoster}
            className="rounded border border-parchment/20 px-4 py-2 text-sm text-parchment/70 hover:bg-parchment/10"
          >
            Reset Roster
          </button>
        </div>
        <div className="flex gap-2">
          <Link
            href="/"
            className="rounded border border-parchment/30 px-4 py-2 text-sm text-parchment/80 hover:bg-parchment/10"
          >
            Cancel
          </Link>
          <button
            onClick={save}
            className="rounded border border-ember bg-ember/40 px-4 py-2 text-sm text-parchment hover:bg-ember/60"
          >
            Save Party
          </button>
        </div>
      </div>
    </main>
  );
}

function RosterCard({
  member, selected, onToggle, onDelete,
}: {
  member: PartyMember;
  selected: boolean;
  onToggle: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className={`rounded border bg-parchment/5 p-3 transition ${
        selected
          ? "border-ember bg-ember/10"
          : "border-parchment/20 hover:border-parchment/40"
      }`}
    >
      <div className="flex items-start justify-between">
        <button
          onClick={onToggle}
          className="flex flex-1 items-center gap-3 text-left"
        >
          <input
            type="checkbox"
            checked={selected}
            readOnly
            className="h-4 w-4 accent-ember"
          />
          <div>
            <div className="font-medium text-parchment">{member.name}</div>
            <div className="text-xs text-parchment/60">
              Level {member.level} {member.race} {member.class}
            </div>
          </div>
        </button>
        <button
          onClick={onDelete}
          aria-label={`Delete ${member.name}`}
          className="rounded px-1 text-xs text-parchment/40 hover:text-red-400"
          title="Remove from roster"
        >
          ✕
        </button>
      </div>
      <div className="mt-2 grid grid-cols-5 gap-1 text-center text-[10px] text-parchment/70">
        <Stat label="STR" value={member.strength} />
        <Stat label="DEX" value={member.dexterity} />
        <Stat label="CON" value={member.constitution} />
        <Stat label="INT" value={member.intelligence} />
        <Stat label="WIS" value={member.wisdom} />
      </div>
      <div className="mt-2 text-[11px] text-parchment/60">
        HP {member.hp}/{member.maxHp}
        {typeof member.maxMp === "number" && member.maxMp > 0 && (
          <> · MP {member.mp ?? 0}/{member.maxMp}</>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded bg-parchment/5 py-1">
      <div className="font-semibold text-parchment">{value}</div>
      <div className="text-[9px] uppercase tracking-wider text-parchment/40">
        {label} {fmtMod(statMod(value))}
      </div>
    </div>
  );
}
