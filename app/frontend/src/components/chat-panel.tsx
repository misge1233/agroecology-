"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Bot,
  Loader2,
  MapPinned,
  Navigation,
  Send,
  Sparkles,
  User,
} from "lucide-react";
import { postRecommend, streamChat } from "@/lib/api";
import type { ChatMessage, ChatSlotsEvent, RecommendResponse } from "@/lib/types";
import { useMetadata } from "./metadata-provider";
import { ContextChips, SuggestionChips } from "./chips";
import { RecommendationPanel } from "./recommendation-card";
import { AssistantMarkdown } from "./assistant-markdown";
import { LocationPicker } from "./location-picker";
import { ChatQuickReplies } from "./chat-quick-replies";
import {
  deriveChatSetup,
  indicatorLabelForFamily,
  type ChatSlotsPayload,
} from "@/lib/chat-flow";
import { Chip } from "./ui/motion";
import { Button } from "./ui/button";

const TOP_N_OPTIONS = [1, 2, 3, 5] as const;

function trimRecommendation(data: RecommendResponse, n: number): RecommendResponse {
  if (data.recommendations.length <= n) return data;
  return {
    ...data,
    recommendations: data.recommendations.slice(0, n),
    details: {
      ...data.details,
      ranked: data.details.ranked.slice(0, n),
    },
  };
}
const EXAMPLES = [
  "I want to reduce soil loss on my sloping field near Debre Birhan",
  "My farm is at 8.38, 39.37 — how do I cut soil erosion?",
  "At 9.03, 38.74 I grow wheat. How can I raise yield?",
];

const MAP_OFFER_RE =
  /\b(map|pin|location|where\s+(is|are)\s+your|drop\s+a\s+pin|latitude|longitude|coordinates)\b/i;
const AFFIRM_RE =
  /^(yes|yeah|yep|sure|ok|okay|please|go ahead|open (the )?map|show (the )?map|i('d| would) like( to)?)\b/i;

interface Turn {
  id: string;
  role: "user" | "assistant";
  content: string;
  recommendation?: RecommendResponse | null;
  showMap?: boolean;
}

export function ChatPanel({ seedMessage }: { seedMessage?: string | null }) {
  const { meta, loading: metaLoading, error: metaError } = useMetadata();
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mapOpen, setMapOpen] = useState(false);
  const [mapLat, setMapLat] = useState<number | null>(null);
  const [mapLon, setMapLon] = useState<number | null>(null);
  const [pendingFamily, setPendingFamily] = useState<string | null>(null);
  const [pendingIndicator, setPendingIndicator] = useState<string | null>(null);
  const [refreshingRec, setRefreshingRec] = useState(false);
  const [topN, setTopN] = useState(1);
  const [reopenChallengePicker, setReopenChallengePicker] = useState(false);
  const [serverSlots, setServerSlots] = useState<ChatSlotsPayload | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const seeded = useRef(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy, mapOpen]);

  useEffect(() => {
    if (seedMessage && !seeded.current) {
      seeded.current = true;
      void send(seedMessage);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedMessage]);

  const history = useMemo<ChatMessage[]>(
    () =>
      turns
        .filter((t) => t.content)
        .map((t) => ({ role: t.role, content: t.content })),
    [turns]
  );

  const lastQuery = useMemo(() => {
    for (let i = turns.length - 1; i >= 0; i--) {
      const q = turns[i].recommendation?.query;
      if (q) return q;
    }
    return null;
  }, [turns]);

  const lastRecommendation = useMemo(() => {
    for (let i = turns.length - 1; i >= 0; i--) {
      if (turns[i].recommendation) return turns[i].recommendation!;
    }
    return null;
  }, [turns]);

  const needsLocation = !lastQuery && !mapLat;

  const derivedSetup = useMemo(
    () =>
      deriveChatSetup(
        turns,
        lastQuery,
        mapLat,
        mapLon,
        meta ?? null,
        serverSlots
      ),
    [turns, lastQuery, mapLat, mapLon, meta, serverSlots]
  );

  const chatSetup = useMemo(() => {
    if (lastQuery) return derivedSetup;
    if (reopenChallengePicker) {
      return {
        stage: "challenge" as const,
        family: null,
        indicatorKey: null,
        hasLocation: derivedSetup.hasLocation,
      };
    }
    return derivedSetup;
  }, [derivedSetup, lastQuery, reopenChallengePicker]);

  async function applyTopN(n: number) {
    setTopN(n);
    if (!lastQuery) return;

    const patchLastRec = (rec: RecommendResponse) => {
      setTurns((prev) => {
        for (let i = prev.length - 1; i >= 0; i--) {
          if (!prev[i].recommendation) continue;
          const next = [...prev];
          next[i] = { ...next[i], recommendation: rec };
          return next;
        }
        return prev;
      });
    };

    const currentLen = lastRecommendation?.recommendations.length ?? 0;
    if (n <= currentLen && lastRecommendation) {
      patchLastRec(trimRecommendation(lastRecommendation, n));
      return;
    }

    setRefreshingRec(true);
    setError(null);
    try {
      const res = await postRecommend({
        lat: lastQuery.lat,
        lon: lastQuery.lon,
        practice_family: lastQuery.practice_family,
        indicator: lastQuery.indicator,
        crop_type: lastQuery.crop_type,
        top_n: n,
      });
      patchLastRec(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load more practices");
    } finally {
      setRefreshingRec(false);
    }
  }

  async function send(text: string) {
    const msg = text.trim();
    if (!msg || busy) return;
    setError(null);
    setInput("");

    // Affirmative reply to map offer → open map UI locally.
    const lastAssistant = [...turns].reverse().find((t) => t.role === "assistant");
    if (
      AFFIRM_RE.test(msg) &&
      lastAssistant &&
      (lastAssistant.showMap || MAP_OFFER_RE.test(lastAssistant.content))
    ) {
      setTurns((prev) => [
        ...prev,
        { id: `u-${Date.now()}`, role: "user", content: msg },
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          content:
            "Great — drop a pin on the map below (or type lat/long). Once set, I'll use that location for recommendations.",
          showMap: true,
        },
      ]);
      setMapOpen(true);
      return;
    }

    const userTurn: Turn = { id: `u-${Date.now()}`, role: "user", content: msg };
    const assistantId = `a-${Date.now()}`;
    if (meta) {
      const fam = msg.match(/^My challenge is (.+)\.$/i)?.[1]?.trim();
      if (fam && meta.practice_families.includes(fam)) {
        setPendingFamily(fam);
        setReopenChallengePicker(false);
      }
      const obj = msg.match(/^My objective is to (.+)\.$/i)?.[1]?.trim();
      if (obj) {
        const ind = meta.indicators.find(
          (i) => i.label.toLowerCase() === obj.toLowerCase()
        );
        if (ind) setPendingIndicator(ind.key);
      }
    }
    setTurns((prev) => [
      ...prev,
      userTurn,
      { id: assistantId, role: "assistant", content: "" },
    ]);
    setBusy(true);

    try {
      let recommendation: RecommendResponse | null = null;
      let reply = "";

      for await (const ev of streamChat({
        message: msg,
        history,
        lastRecommendation,
        topN,
      })) {
        if (ev.type === "slots" && ev.data) {
          const slots = ev.data as ChatSlotsEvent;
          setServerSlots(slots);
          if (slots.practice_family) {
            setPendingFamily(slots.practice_family);
            setReopenChallengePicker(false);
          }
          if (slots.indicator) setPendingIndicator(slots.indicator);
          if (slots.lat != null && slots.lon != null) {
            setMapLat(Number(slots.lat.toFixed(4)));
            setMapLon(Number(slots.lon.toFixed(4)));
          }
        }
        if (ev.type === "recommendation" && ev.data) {
          recommendation = trimRecommendation(
            ev.data as RecommendResponse,
            topN
          );
          const rec = recommendation;
          setTurns((prev) =>
            prev.map((t) =>
              t.id === assistantId ? { ...t, recommendation: rec } : t
            )
          );
        }
        if (ev.type === "token" && ev.text) {
          reply += ev.text;
          const snapshot = reply;
          setTurns((prev) =>
            prev.map((t) =>
              t.id === assistantId ? { ...t, content: snapshot } : t
            )
          );
        }
        if (ev.type === "error") {
          setError(ev.message || "Chat failed");
        }
      }

      if (recommendation) {
        const rec = recommendation;
        setTurns((prev) =>
          prev.map((t) =>
            t.id === assistantId ? { ...t, recommendation: rec } : t
          )
        );
      } else if (reply && MAP_OFFER_RE.test(reply) && needsLocation) {
        setTurns((prev) =>
          prev.map((t) =>
            t.id === assistantId ? { ...t, showMap: true } : t
          )
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chat failed");
      setTurns((prev) =>
        prev.map((t) =>
          t.id === assistantId && !t.content
            ? {
                ...t,
                content:
                  "Something went wrong reaching the assistant. Try the form, or retry.",
              }
            : t
        )
      );
    } finally {
      setBusy(false);
    }
  }

  function applyMapAndContinue() {
    if (mapLat == null || mapLon == null) return;
    const bits = [
      `My farm is at ${mapLat.toFixed(4)}, ${mapLon.toFixed(4)}.`,
      pendingFamily ? `Challenge: ${pendingFamily}.` : null,
      pendingIndicator
        ? `Objective: ${
            meta?.indicators.find((i) => i.key === pendingIndicator)?.label ||
            pendingIndicator
          }.`
        : null,
    ].filter(Boolean);
    setMapOpen(false);
    void send(bits.join(" "));
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      setError("Geolocation is not available in this browser.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const la = Number(pos.coords.latitude.toFixed(4));
        const lo = Number(pos.coords.longitude.toFixed(4));
        setMapLat(la);
        setMapLon(lo);
        setMapOpen(true);
        void send(`My farm is at ${la}, ${lo}.`);
      },
      () => setError("Could not read your location. Try the map instead."),
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  const showQuickReplies =
    !busy &&
    turns.length > 0 &&
    !lastQuery &&
    turns[turns.length - 1]?.role === "assistant" &&
    !!turns[turns.length - 1]?.content &&
    !turns[turns.length - 1]?.recommendation;

  return (
    <div className="relative flex h-[calc(100dvh-var(--header-h))] flex-col bg-[radial-gradient(ellipse_60%_40%_at_50%_-6%,color-mix(in_oklab,var(--leaf)_7%,transparent),transparent_70%)]">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl space-y-5 px-4 py-5 sm:px-6 sm:py-8 lg:max-w-4xl">
          {turns.length === 0 && (
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
              className="flex min-h-[min(56vh,480px)] flex-col items-center justify-center text-center"
            >
              <p className="eyebrow mb-4 inline-flex items-center gap-2 rounded-lg border border-edge bg-elevated px-3.5 py-1.5 normal-case tracking-normal shadow-sm">
                <Sparkles className="h-3.5 w-3.5 text-leaf" />
                <span className="text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
                  CSA practice advisor
                </span>
              </p>
              <h1 className="font-display text-[2.4rem] font-semibold leading-[1.08] tracking-tight text-ink sm:text-[3.1rem]">
                Describe the farm context.
                <span className="block text-body">Receive best CSA practice</span>
              </h1>
              <p className="mt-4 max-w-lg text-[15px] leading-relaxed text-mute sm:text-base">
                Describe your farm in plain language — place name or map pin, challenge,
                and goal. Practices are ranked from field evidence for your zone, not
                invented advice.
              </p>

              <div className="mt-8 w-full max-w-xl">
                <Composer
                  id="chat-input-hero"
                  value={input}
                  onChange={setInput}
                  onSend={() => void send(input)}
                  busy={busy}
                  placeholder="Ask about yield, soil loss, runoff…"
                  large
                />
              </div>

              <div className="mt-6 flex flex-wrap justify-center gap-2">
                <Chip onClick={() => setMapOpen(true)}>
                  <MapPinned className="h-3.5 w-3.5" /> Pick on map
                </Chip>
                <Chip onClick={useMyLocation}>
                  <Navigation className="h-3.5 w-3.5" /> Use my location
                </Chip>
              </div>

              <div className="mt-7 w-full space-y-3">
                <p className="text-[11px] font-medium uppercase tracking-widest text-mute">
                  Try an example
                </p>
                <SuggestionChips items={EXAMPLES} onPick={(t) => void send(t)} />
              </div>

              {(metaLoading || metaError) && (
                <p className="mt-4 text-xs text-mute">
                  {metaLoading
                    ? "Loading model metadata…"
                    : `Backend unreachable: ${metaError}`}
                </p>
              )}
            </motion.div>
          )}

          <AnimatePresence initial={false}>
            {turns.map((t) => (
              <motion.div
                key={t.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className={
                  t.role === "user" ? "flex justify-end gap-2" : "flex justify-start gap-2"
                }
              >
                {t.role === "assistant" && (
                  <span className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-leaf text-white shadow-soft">
                    <Bot className="h-4 w-4" aria-hidden />
                  </span>
                )}
                <div
                  className={
                    t.role === "user"
                      ? "max-w-[88%] rounded-[22px] rounded-br-md bg-ink px-4 py-3 text-[15px] leading-relaxed text-elevated shadow-lift"
                      : "max-w-[94%] space-y-3"
                  }
                >
                  {t.role === "assistant" ? (
                    <>
                      {t.content ? (
                        <div className="rounded-[22px] rounded-bl-md border border-edge/80 bg-elevated/95 px-4 py-3.5 shadow-soft backdrop-blur sm:px-5">
                          <AssistantMarkdown content={t.content} />
                          {busy &&
                            turns[turns.length - 1]?.id === t.id &&
                            !t.recommendation && (
                              <Loader2 className="ml-1 inline h-3.5 w-3.5 animate-spin text-mute" />
                            )}
                        </div>
                      ) : (
                        busy &&
                        turns[turns.length - 1]?.id === t.id && (
                          <div className="inline-flex items-center gap-2 rounded-[22px] border border-edge bg-elevated px-4 py-3 text-sm text-mute shadow-soft">
                            <Loader2 className="h-4 w-4 animate-spin text-leaf" />
                            Thinking…
                          </div>
                        )
                      )}
                      {t.showMap && meta && (
                        <MapOfferCard
                          onOpen={() => setMapOpen(true)}
                          open={mapOpen && turns[turns.length - 1]?.id === t.id}
                        />
                      )}
                      {t.recommendation && (
                        <div className="overflow-hidden rounded-[1.75rem] border border-edge/90 bg-elevated/98 shadow-lift backdrop-blur sm:rounded-[28px]">
                          <RecommendationPanel
                            data={t.recommendation}
                            variant="hero"
                          />
                        </div>
                      )}
                    </>
                  ) : (
                    t.content
                  )}
                </div>
                {t.role === "user" && (
                  <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink text-elevated">
                    <User className="h-4 w-4" aria-hidden />
                  </span>
                )}
              </motion.div>
            ))}
          </AnimatePresence>

          {showQuickReplies && meta && (
            <ChatQuickReplies
              meta={meta}
              setup={chatSetup}
              onPickChallenge={(f) => {
                setPendingFamily(f);
                setReopenChallengePicker(false);
                void send(`My challenge is ${f}.`);
              }}
              onPickObjective={(ind) => {
                setPendingIndicator(ind.key);
                void send(`My objective is to ${ind.label.toLowerCase()}.`);
              }}
              onChangeChallenge={() => {
                setReopenChallengePicker(true);
                setPendingFamily(null);
                setPendingIndicator(null);
              }}
              onOpenMap={() => setMapOpen(true)}
              onUseLocation={useMyLocation}
            />
          )}

          {mapOpen && meta && (
            <div className="rounded-[28px] border border-edge bg-elevated/95 p-4 shadow-lift sm:p-5">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h2 className="font-display text-xl tracking-tight text-ink">
                  Pick your farm location
                </h2>
                <button
                  type="button"
                  className="text-xs font-medium text-mute hover:text-ink"
                  onClick={() => setMapOpen(false)}
                >
                  Close
                </button>
              </div>
              <LocationPicker
                lat={mapLat}
                lon={mapLon}
                bounds={meta.bounds}
                onChange={(la, lo) => {
                  setMapLat(la);
                  setMapLon(lo);
                }}
              />
              <div className="mt-4 flex justify-end">
                <Button
                  variant="gradient"
                  disabled={mapLat == null || mapLon == null}
                  onClick={applyMapAndContinue}
                >
                  Use this location
                </Button>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <div className="mx-auto w-full max-w-3xl shrink-0 border-t border-edge/60 bg-canvas/85 px-4 pb-5 pt-3 backdrop-blur-md sm:px-6 lg:max-w-4xl">
        {lastQuery && (
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-edge/80 bg-elevated/70 px-3 py-2.5 shadow-sm">
            <p className="text-[13px] font-medium text-ink">
              Practices shown
              {refreshingRec && (
                <Loader2 className="ml-2 inline h-3.5 w-3.5 animate-spin text-mute" />
              )}
            </p>
            <div className="flex gap-1 rounded-full bg-panel/80 p-1">
              {TOP_N_OPTIONS.map((n) => (
                <button
                  key={n}
                  type="button"
                  disabled={refreshingRec || busy}
                  onClick={() => void applyTopN(n)}
                  className={
                    topN === n
                      ? "rounded-lg bg-leaf px-3.5 py-1.5 text-[13px] font-semibold text-white shadow-sm"
                      : "rounded-full px-3.5 py-1.5 text-[13px] font-medium text-mute transition hover:text-ink"
                  }
                >
                  {n === 1 ? "Top 1" : `Top ${n}`}
                </button>
              ))}
            </div>
          </div>
        )}
        {meta && turns.length > 0 && !lastQuery && chatSetup.stage !== "complete" && (
          <div className="mb-2 flex flex-wrap items-center gap-2 rounded-2xl border border-edge/60 bg-elevated/50 px-3 py-2 text-[12px] text-mute">
            <span className="font-medium text-ink">Your setup</span>
            <span aria-hidden>·</span>
            <span>
              {chatSetup.family ? chatSetup.family.replace(/ and management$/i, "") : "Challenge"}
            </span>
            <span aria-hidden>→</span>
            <span>
              {chatSetup.indicatorKey
                ? indicatorLabelForFamily(
                    chatSetup.family,
                    meta.indicators.find((i) => i.key === chatSetup.indicatorKey) ?? {
                      key: chatSetup.indicatorKey,
                      label: chatSetup.indicatorKey,
                      direction: "increase",
                    }
                  )
                : "Objective"}
            </span>
            <span aria-hidden>→</span>
            <span>{chatSetup.hasLocation ? "Location set" : "Location"}</span>
          </div>
        )}

        {lastQuery && (
          <div className="mb-2">
            <ContextChips
              slots={{
                lat: lastQuery.lat,
                lon: lastQuery.lon,
                challenge: lastQuery.practice_family,
                objective: lastQuery.indicator,
                crop: lastQuery.crop_type ?? undefined,
              }}
            />
          </div>
        )}
        {error && (
          <p className="mb-2 text-xs text-soil" role="alert">
            {error}{" "}
            <button
              type="button"
              className="underline"
              onClick={() => setError(null)}
            >
              dismiss
            </button>
          </p>
        )}
        {(turns.length > 0 || mapOpen) && (
          <Composer
            id="chat-input"
            value={input}
            onChange={setInput}
            onSend={() => void send(input)}
            busy={busy}
            placeholder="Describe your farm and goal…"
            onMap={() => setMapOpen(true)}
          />
        )}
      </div>
    </div>
  );
}

function Composer({
  id,
  value,
  onChange,
  onSend,
  busy,
  placeholder,
  large,
  onMap,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  busy: boolean;
  placeholder: string;
  large?: boolean;
  onMap?: () => void;
}) {
  return (
    <form
      className="flex items-end gap-2 rounded-2xl border border-edge bg-elevated p-1.5 shadow-soft"
      onSubmit={(e) => {
        e.preventDefault();
        onSend();
      }}
    >
      {onMap && (
        <button
          type="button"
          onClick={onMap}
          className="mb-0.5 rounded-lg p-2.5 text-mute transition hover:bg-panel hover:text-ink"
          aria-label="Open map"
        >
          <MapPinned className="h-4 w-4" />
        </button>
      )}
      <label className="sr-only" htmlFor={id}>
        Message
      </label>
      <textarea
        id={id}
        rows={large ? 2 : 1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSend();
          }
        }}
        placeholder={placeholder}
        className={
          large
            ? "max-h-28 min-h-[56px] flex-1 resize-none bg-transparent px-3 py-3 text-[15px] text-ink outline-none placeholder:text-mute/80"
            : "max-h-32 min-h-[44px] flex-1 resize-none bg-transparent px-3.5 py-2.5 text-sm text-ink outline-none placeholder:text-mute"
        }
        disabled={busy}
      />
      <button
        type="submit"
        disabled={busy || !value.trim()}
        className={
          large
            ? "mb-0.5 inline-flex h-11 shrink-0 items-center gap-1.5 rounded-xl bg-leaf px-4 text-[13px] font-semibold text-white shadow-soft transition hover:bg-leaf-deep disabled:opacity-35"
            : "inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-leaf text-white shadow-soft transition hover:bg-leaf-deep disabled:opacity-35"
        }
        aria-label="Send"
      >
        {busy ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : large ? (
          <>
            Ask
            <Send className="h-3.5 w-3.5" />
          </>
        ) : (
          <Send className="h-4 w-4" />
        )}
      </button>
    </form>
  );
}

function MapOfferCard({
  onOpen,
  open,
}: {
  onOpen: () => void;
  open?: boolean;
}) {
  if (open) return null;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-3 rounded-2xl border border-dashed border-leaf/40 bg-leaf/5 px-4 py-3 text-left transition hover:bg-leaf/10"
    >
      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-leaf/15 text-leaf-deep dark:text-leaf-bright">
        <MapPinned className="h-5 w-5" />
      </span>
      <span>
        <span className="block text-sm font-semibold text-ink">
          Open map to drop a pin
        </span>
        <span className="block text-xs text-mute">
          Ethiopia bounds validated · lat/long stay in sync
        </span>
      </span>
    </button>
  );
}
