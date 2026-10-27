"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Bot, Loader2, MapPinned, Navigation, Send, Sparkles, User, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { postRecommend, streamChat } from "@/lib/api";
import type { ChatMessage, ChatSlotsEvent, RecommendResponse } from "@/lib/types";
import { deriveChatSetup, type ChatSlotsPayload } from "@/lib/chat-flow";
import { familyShort, indicatorLabel } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { cn } from "@/lib/utils";
import { useMetadata } from "./metadata-provider";
import { AssistantMarkdown } from "./assistant-markdown";
import { ChatQuickReplies } from "./chat-quick-replies";
import { RecommendationPanel } from "./advisor/recommendation-panel";
import { LocationPicker } from "./advisor/location-step";
import { useZone } from "./advisor/use-zone";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Chip } from "./ui/chip";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "./ui/sheet";

const TOP_N_OPTIONS = [1, 2, 3, 5] as const;

function trimRecommendation(data: RecommendResponse, n: number): RecommendResponse {
  if (data.recommendations.length <= n) return data;
  return {
    ...data,
    recommendations: data.recommendations.slice(0, n),
    details: { ...data.details, ranked: data.details.ranked.slice(0, n) },
  };
}

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

/**
 * The conversational advisor. Logic is unchanged from P5 (slots, protocol
 * messages, map offer); U1 restyles it on the design system, moves every
 * string to the catalog and sends the UI language to the backend. A seed
 * message (from the Advisor's "Explain in chat") pre-fills the composer —
 * the user sends it, nothing fires on mount.
 */
export function ChatPanel({ seedMessage }: { seedMessage?: string | null }) {
  const t = useTranslations("chat");
  const tc = useTranslations("common");
  const locale = useLocale() as Locale;
  const { meta, loading: metaLoading, error: metaError } = useMetadata();
  const [input, setInput] = useState(seedMessage ?? "");
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
  const zone = useZone(mapLat, mapLon, meta?.bounds ?? null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, busy]);

  const history = useMemo<ChatMessage[]>(
    () => turns.filter((x) => x.content).map((x) => ({ role: x.role, content: x.content })),
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
    () => deriveChatSetup(turns, lastQuery, mapLat, mapLon, meta ?? null, serverSlots),
    [turns, lastQuery, mapLat, mapLon, meta, serverSlots]
  );
  const chatSetup = useMemo(() => {
    if (lastQuery) return derivedSetup;
    if (reopenChallengePicker) {
      return { stage: "challenge" as const, family: null, indicatorKey: null, hasLocation: derivedSetup.hasLocation };
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
      setError(e instanceof Error ? e.message : t("loadMoreFailed"));
    } finally {
      setRefreshingRec(false);
    }
  }

  async function send(text: string) {
    const msg = text.trim();
    if (!msg || busy) return;
    setError(null);
    setInput("");

    // Affirmative reply to a map offer → open the map locally.
    const lastAssistant = [...turns].reverse().find((x) => x.role === "assistant");
    if (AFFIRM_RE.test(msg) && lastAssistant && (lastAssistant.showMap || MAP_OFFER_RE.test(lastAssistant.content))) {
      setTurns((prev) => [
        ...prev,
        { id: `u-${Date.now()}`, role: "user", content: msg },
        { id: `a-${Date.now()}`, role: "assistant", content: t("mapOfferReply"), showMap: true },
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
        const ind = meta.indicators.find((i) => i.label.toLowerCase() === obj.toLowerCase());
        if (ind) setPendingIndicator(ind.key);
      }
    }
    setTurns((prev) => [...prev, userTurn, { id: assistantId, role: "assistant", content: "" }]);
    setBusy(true);

    try {
      let recommendation: RecommendResponse | null = null;
      let reply = "";
      for await (const ev of streamChat({ message: msg, history, lastRecommendation, topN, language: locale })) {
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
          recommendation = trimRecommendation(ev.data as RecommendResponse, topN);
          const rec = recommendation;
          setTurns((prev) => prev.map((x) => (x.id === assistantId ? { ...x, recommendation: rec } : x)));
        }
        if (ev.type === "token" && ev.text) {
          reply += ev.text;
          const snapshot = reply;
          setTurns((prev) => prev.map((x) => (x.id === assistantId ? { ...x, content: snapshot } : x)));
        }
        if (ev.type === "error") setError(ev.message || t("chatFailed"));
      }
      if (recommendation) {
        const rec = recommendation;
        setTurns((prev) => prev.map((x) => (x.id === assistantId ? { ...x, recommendation: rec } : x)));
      } else if (reply && MAP_OFFER_RE.test(reply) && needsLocation) {
        setTurns((prev) => prev.map((x) => (x.id === assistantId ? { ...x, showMap: true } : x)));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("chatFailed"));
      setTurns((prev) =>
        prev.map((x) => (x.id === assistantId && !x.content ? { ...x, content: t("errorFallback") } : x))
      );
    } finally {
      setBusy(false);
    }
  }

  function applyMapAndContinue() {
    if (mapLat == null || mapLon == null) return;
    const bits = [
      t("protocol.farmAt", { lat: mapLat.toFixed(4), lon: mapLon.toFixed(4) }),
      pendingFamily ? t("protocol.challengeNote", { family: pendingFamily }) : null,
      pendingIndicator
        ? t("protocol.objectiveNote", {
            objective: meta?.indicators.find((i) => i.key === pendingIndicator)?.label || pendingIndicator,
          })
        : null,
    ].filter(Boolean);
    setMapOpen(false);
    void send(bits.join(" "));
  }

  function useMyLocation() {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setError(t("geoUnavailable"));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const la = Number(pos.coords.latitude.toFixed(4));
        const lo = Number(pos.coords.longitude.toFixed(4));
        setMapLat(la);
        setMapLon(lo);
        void send(t("protocol.farmAt", { lat: la.toFixed(4), lon: lo.toFixed(4) }));
      },
      () => setError(t("geoFailed")),
      { enableHighAccuracy: true, timeout: 10_000 }
    );
  }

  const showQuickReplies =
    !busy &&
    turns.length > 0 &&
    !lastQuery &&
    turns[turns.length - 1]?.role === "assistant" &&
    !!turns[turns.length - 1]?.content &&
    !turns[turns.length - 1]?.recommendation;

  const examples = [t("examples.one"), t("examples.two"), t("examples.three")];

  return (
    <div className="flex h-[calc(100dvh-var(--header-h)-var(--bottombar-h))] flex-col md:h-[calc(100dvh-var(--header-h))]">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl space-y-5 px-4 py-5 sm:px-6 sm:py-8">
          {turns.length === 0 ? (
            <div className="flex min-h-[min(56vh,480px)] flex-col items-center justify-center text-center">
              <p className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3.5 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-muted">
                <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden />
                {t("eyebrow")}
              </p>
              <h1 className="mt-5 text-balance text-3xl sm:text-4xl">
                {t("title")}
                <span className="block text-muted">{t("titleLine2")}</span>
              </h1>
              <p className="mt-4 max-w-lg text-base text-muted">{t("intro")}</p>

              <div className="mt-8 w-full max-w-xl">
                <Composer
                  id="chat-input-hero"
                  value={input}
                  onChange={setInput}
                  onSend={() => void send(input)}
                  busy={busy}
                  placeholder={t("placeholderHero")}
                  large
                />
              </div>

              <div className="mt-5 flex flex-wrap justify-center gap-2">
                <Chip onClick={() => setMapOpen(true)} icon={<MapPinned className="h-4 w-4 text-primary" aria-hidden />}>
                  {t("pickOnMap")}
                </Chip>
                <Chip onClick={useMyLocation} icon={<Navigation className="h-4 w-4 text-primary" aria-hidden />}>
                  {t("useMyLocation")}
                </Chip>
              </div>

              <div className="mt-7 w-full space-y-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">{t("tryExample")}</p>
                <div className="flex flex-wrap justify-center gap-2">
                  {examples.map((ex) => (
                    <button
                      key={ex}
                      type="button"
                      onClick={() => void send(ex)}
                      className="rounded-control border border-border bg-surface px-3.5 py-2 text-left text-sm text-text transition-colors duration-base hover:border-primary/50 hover:bg-surface-2"
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              </div>

              {metaLoading || metaError ? (
                <p className="mt-4 text-xs text-muted">
                  {metaLoading ? t("loadingMeta") : t("backendUnreachable", { error: metaError ?? "" })}
                </p>
              ) : null}
            </div>
          ) : null}

          {turns.map((turn) => (
            <div key={turn.id} className={cn("rise-in flex gap-2", turn.role === "user" ? "justify-end" : "justify-start")}>
              {turn.role === "assistant" ? (
                <span className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-control bg-primary text-primary-fg">
                  <Bot className="h-4 w-4" aria-hidden />
                </span>
              ) : null}
              <div className={turn.role === "user" ? "max-w-[88%] rounded-card rounded-br-sm bg-text px-4 py-3 text-base text-background" : "max-w-[94%] min-w-0 flex-1 space-y-3"}>
                {turn.role === "assistant" ? (
                  <>
                    {turn.content ? (
                      <div className="rounded-card rounded-bl-sm border border-border bg-surface px-4 py-3.5 shadow-1 sm:px-5">
                        <AssistantMarkdown content={turn.content} />
                        {busy && turns[turns.length - 1]?.id === turn.id && !turn.recommendation ? (
                          <Loader2 className="ml-1 inline h-3.5 w-3.5 animate-spin text-muted" aria-hidden />
                        ) : null}
                      </div>
                    ) : busy && turns[turns.length - 1]?.id === turn.id ? (
                      <div className="inline-flex items-center gap-2 rounded-card border border-border bg-surface px-4 py-3 text-sm text-muted" role="status">
                        <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden />
                        {t("thinking")}
                      </div>
                    ) : null}
                    {turn.showMap && meta && !mapOpen ? (
                      <button
                        type="button"
                        onClick={() => setMapOpen(true)}
                        className="flex w-full items-center gap-3 rounded-card border border-dashed border-primary/50 bg-primary-soft/60 px-4 py-3 text-left transition-colors duration-base hover:bg-primary-soft"
                      >
                        <span className="flex h-10 w-10 items-center justify-center rounded-control bg-primary text-primary-fg">
                          <MapPinned className="h-5 w-5" aria-hidden />
                        </span>
                        <span>
                          <span className="block text-sm font-semibold text-text">{t("mapOffer.title")}</span>
                          <span className="block text-xs text-muted">{t("mapOffer.body")}</span>
                        </span>
                      </button>
                    ) : null}
                    {turn.recommendation ? <RecommendationPanel data={turn.recommendation} /> : null}
                  </>
                ) : (
                  turn.content
                )}
              </div>
              {turn.role === "user" ? (
                <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-2 text-text">
                  <User className="h-4 w-4" aria-hidden />
                </span>
              ) : null}
            </div>
          ))}

          {showQuickReplies && meta ? (
            <ChatQuickReplies
              meta={meta}
              setup={chatSetup}
              onPickChallenge={(f) => {
                setPendingFamily(f);
                setReopenChallengePicker(false);
                void send(t("protocol.challenge", { family: f }));
              }}
              onPickObjective={(key) => {
                const ind = meta.indicators.find((i) => i.key === key);
                setPendingIndicator(key);
                void send(t("protocol.objective", { objective: (ind?.label ?? key).toLowerCase() }));
              }}
              onChangeChallenge={() => {
                setReopenChallengePicker(true);
                setPendingFamily(null);
                setPendingIndicator(null);
              }}
              onOpenMap={() => setMapOpen(true)}
              onUseLocation={useMyLocation}
            />
          ) : null}

          <div ref={bottomRef} />
        </div>
      </div>

      <div className="mx-auto w-full max-w-3xl shrink-0 border-t border-border bg-background/95 px-4 pb-4 pt-3 backdrop-blur sm:px-6">
        {lastQuery ? (
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm font-medium text-text">
              {t("practicesShown")}
              {refreshingRec ? <Loader2 className="ml-2 inline h-3.5 w-3.5 animate-spin text-muted" aria-hidden /> : null}
            </p>
            <div className="flex gap-1" role="group" aria-label={t("practicesShown")}>
              {TOP_N_OPTIONS.map((n) => (
                <Chip key={n} selected={topN === n} disabled={refreshingRec || busy} onClick={() => void applyTopN(n)} className="min-h-9 px-3 py-1">
                  {t("topN", { n })}
                </Chip>
              ))}
            </div>
          </div>
        ) : null}

        {meta && turns.length > 0 && !lastQuery && chatSetup.stage !== "complete" ? (
          <p className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted">
            <span className="font-medium text-text">{t("yourSetup")}</span>
            <span aria-hidden>·</span>
            <span>{chatSetup.family ? familyShort(chatSetup.family, locale) : t("stage.challenge")}</span>
            <span aria-hidden>·</span>
            <span>{chatSetup.indicatorKey ? indicatorLabel(chatSetup.indicatorKey, locale) : t("stage.objective")}</span>
            <span aria-hidden>·</span>
            <span>{chatSetup.hasLocation ? t("stage.locationSet") : t("stage.location")}</span>
          </p>
        ) : null}

        {lastQuery ? (
          <ul className="mb-2 flex flex-wrap gap-1.5" aria-label={t("contextChips.label")}>
            {(
              [
                ["lat", String(lastQuery.lat)],
                ["lon", String(lastQuery.lon)],
                ["challenge", familyShort(lastQuery.practice_family, locale)],
                ["objective", indicatorLabel(lastQuery.indicator, locale)],
                ["crop", lastQuery.crop_type ?? ""],
              ] as const
            )
              .filter(([, v]) => v)
              .map(([k, v]) => (
                <li key={k}>
                  <Badge variant="outline-neutral" className="font-normal">
                    <span>{t(`contextChips.${k}`)}:</span>
                    <span className="font-medium text-text">{v}</span>
                  </Badge>
                </li>
              ))}
          </ul>
        ) : null}

        {error ? (
          <p className="mb-2 flex items-center gap-2 text-sm text-danger-text" role="alert">
            {error}
            <button type="button" className="underline" onClick={() => setError(null)}>
              {tc("dismiss")}
            </button>
          </p>
        ) : null}

        {turns.length > 0 ? (
          <Composer
            id="chat-input"
            value={input}
            onChange={setInput}
            onSend={() => void send(input)}
            busy={busy}
            placeholder={t("placeholder")}
            onMap={() => setMapOpen(true)}
          />
        ) : null}
      </div>

      <Sheet open={mapOpen && !!meta} onOpenChange={setMapOpen}>
        <SheetContent closeLabel={tc("close")} className="sm:max-w-2xl">
          <SheetHeader>
            <SheetTitle>{t("pickLocation")}</SheetTitle>
            <SheetDescription>{t("quick.locationHelp")}</SheetDescription>
          </SheetHeader>
          {meta ? (
            <LocationPicker
              lat={mapLat}
              lon={mapLon}
              bounds={meta.bounds}
              zone={zone}
              onChange={(la, lo) => {
                setMapLat(la);
                setMapLon(lo);
              }}
              mapClassName="h-56 overflow-hidden rounded-card border border-border sm:h-64"
            />
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setMapOpen(false)}>
              <X className="h-4 w-4" aria-hidden />
              {tc("close")}
            </Button>
            <Button disabled={mapLat == null || mapLon == null} onClick={applyMapAndContinue}>
              {t("useThisLocation")}
            </Button>
          </div>
        </SheetContent>
      </Sheet>
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
  const t = useTranslations("chat");
  return (
    <form
      className="flex items-end gap-2 rounded-card border border-border bg-surface p-1.5 shadow-1 focus-within:border-primary/60"
      onSubmit={(e) => {
        e.preventDefault();
        onSend();
      }}
    >
      {onMap ? (
        <Button type="button" variant="ghost" size="icon" onClick={onMap} aria-label={t("pickOnMap")} className="mb-0.5 h-10 w-10">
          <MapPinned className="h-4 w-4" aria-hidden />
        </Button>
      ) : null}
      <label className="sr-only" htmlFor={id}>
        {t("message")}
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
        className={cn(
          "flex-1 resize-none bg-transparent px-3 text-text outline-none placeholder:text-muted",
          large ? "max-h-28 min-h-[56px] py-3 text-base" : "max-h-32 min-h-[44px] py-2.5 text-sm"
        )}
        disabled={busy}
      />
      <Button
        type="submit"
        size={large ? "lg" : "icon"}
        disabled={busy || !value.trim()}
        loading={busy}
        aria-label={large ? undefined : t("send")}
        className="mb-0.5"
      >
        {large ? t("ask") : null}
        {!busy ? <Send className="h-4 w-4" aria-hidden /> : null}
      </Button>
    </form>
  );
}
