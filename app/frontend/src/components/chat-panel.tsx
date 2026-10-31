"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Check, Copy, Leaf, Loader2, MapPin, Mic, Mountain, Send, Sparkles, Square, SquarePen, Volume2, VolumeX, Wheat, X } from "lucide-react";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { streamChat } from "@/lib/api";
import type { AdvisoryEvent, ChatMessage, RecommendQuery, RecommendResponse } from "@/lib/types";
import type { Locale } from "@/i18n/routing";
import { cn } from "@/lib/utils";
import { useSpeaker, useSpeechCapabilities, useVoiceInput, type VoiceError } from "@/lib/speech";
import { useMetadata } from "./metadata-provider";
import { AssistantMarkdown } from "./assistant-markdown";
import { ChatEvidence } from "./chat/chat-evidence";
import { Alert } from "./ui/alert";
import { Button } from "./ui/button";

/** Practices scored per answer: enough for the reply to name alternatives. */
const TOP_N = 3;

type TurnStatus = "thinking" | "scoring" | "streaming" | "done" | "error";

interface Turn {
  id: string;
  role: "user" | "assistant";
  content: string;
  at: number;
  recommendation?: RecommendResponse | null;
  /** P9: the evidence mode, its reasons and the documented practices behind this answer. */
  advisory?: AdvisoryEvent | null;
  /** The advisory's resolved slots as a query (a knowledge-led answer has no model payload). */
  advisoryQuery?: RecommendQuery | null;
  /** The user spoke this message: marked with a mic and answered aloud. */
  viaVoice?: boolean;
  status?: TurnStatus;
  error?: string | null;
}

let seq = 0;
const nextId = (prefix: string) => `${prefix}-${Date.now()}-${++seq}`;
/** Wall-clock stamp for a turn (kept outside the component: event-time, not render-time). */
const stamp = () => Date.now();

/**
 * The conversational advisor (U6). Entirely a conversation: the user types or
 * speaks, the assistant asks in words for whatever is still missing (challenge,
 * objective, location as a place name or coordinates; slot filling is the
 * backend's), then answers in words with a compact evidence attachment. No
 * forms, pickers or quick-reply buttons: the Advisor page is the form.
 * Voice is hands-free: a spoken question is sent when the speaker pauses and
 * its answer is read aloud when ready. A seed message (Advisor "Explain in
 * chat") only pre-fills the composer; nothing is sent on mount.
 */
export function ChatPanel({ seedMessage }: { seedMessage?: string | null }) {
  const t = useTranslations("chat");
  const tc = useTranslations("common");
  const ta = useTranslations("a11y");
  const locale = useLocale() as Locale;
  const format = useFormatter();
  const { loading: metaLoading, error: metaError } = useMetadata();
  const [input, setInput] = useState(seedMessage ?? "");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Voice: speak the question, hear the answer.
  const caps = useSpeechCapabilities(locale);
  const speaker = useSpeaker({ lang: locale, engine: caps.output, voice: caps.voice });
  const [autoRead, setAutoRead] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const sendRef = useRef<(text: string, opts?: { voice?: boolean }) => Promise<void>>(async () => {});
  const onVoiceText = useCallback((text: string) => {
    setError(null);
    const draft = inputRef.current?.value.trim() ?? "";
    void sendRef.current(draft ? `${draft} ${text}` : text, { voice: true });
  }, []);
  const onVoiceError = useCallback(
    (e: VoiceError) => {
      const key = e === "denied" ? "denied" : e === "no-speech" ? "noSpeech" : e === "unsupported-language" ? "unsupportedLanguage" : "failed";
      setError(t(`voice.errors.${key}`));
    },
    [t]
  );
  const voice = useVoiceInput({ lang: locale, engine: caps.input, onText: onVoiceText, onError: onVoiceError });

  useEffect(() => {
    // Follow the conversation; the empty welcome view stays at the top.
    if (turns.length === 0) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, busy]);

  const history = useMemo<ChatMessage[]>(
    () => turns.filter((x) => x.content).map((x) => ({ role: x.role, content: x.content })),
    [turns]
  );
  const lastRecommendation = useMemo(() => {
    for (let i = turns.length - 1; i >= 0; i--) {
      if (turns[i].recommendation) return turns[i].recommendation!;
    }
    return null;
  }, [turns]);

  function patch(id: string, fn: (turn: Turn) => Turn) {
    setTurns((prev) => prev.map((x) => (x.id === id ? fn(x) : x)));
  }

  async function send(text: string, opts: { voice?: boolean } = {}) {
    const msg = text.trim();
    if (!msg || busy) return;
    setError(null);
    setInput("");
    // Spoken questions get spoken answers; typed ones only when "read aloud" is on.
    const readAloud = (!!opts.voice || autoRead) && !!caps.output;
    speaker.stop();

    const userTurn: Turn = { id: nextId("u"), role: "user", content: msg, at: stamp(), viaVoice: !!opts.voice };
    const assistantId = nextId("a");
    setTurns((prev) => [...prev, userTurn, { id: assistantId, role: "assistant", content: "", at: stamp(), status: "thinking" }]);
    setBusy(true);

    let reply = "";
    try {
      for await (const ev of streamChat({ message: msg, history, lastRecommendation, topN: TOP_N, language: locale, hint: null })) {
        if (ev.type === "slots" && ev.data) {
          const s = ev.data as { practice_family?: string | null; indicator?: string | null; lat?: number | null; lon?: number | null };
          const complete = !!(s.practice_family && s.indicator && s.lat != null && s.lon != null);
          patch(assistantId, (x) => ({ ...x, status: complete ? "scoring" : "thinking" }));
        }
        if (ev.type === "advisory" && ev.data) {
          const advisory = ev.data as AdvisoryEvent;
          const advisoryQuery: RecommendQuery | null = advisory.query ? { ...advisory.query, goal_direction: "" } : null;
          patch(assistantId, (x) => ({ ...x, advisory, advisoryQuery }));
        }
        if (ev.type === "recommendation" && ev.data) {
          const rec = ev.data as RecommendResponse;
          patch(assistantId, (x) => ({ ...x, recommendation: rec, status: "streaming" }));
        }
        if (ev.type === "token" && ev.text) {
          reply += ev.text;
          const snapshot = reply;
          patch(assistantId, (x) => ({ ...x, content: snapshot, status: "streaming" }));
        }
        if (ev.type === "error") {
          const message = ev.message || t("chatFailed");
          patch(assistantId, (x) => ({ ...x, status: "error", error: message }));
        }
      }
      patch(assistantId, (x) => (x.status === "error" ? x : { ...x, status: "done", at: stamp() }));
      if (readAloud && reply) {
        void speaker.speak(assistantId, reply).then((ok) => {
          if (!ok) setError(t("voice.errors.ttsFailed"));
        });
      }
    } catch (e) {
      const message = e instanceof Error && e.message ? e.message : t("errorFallback");
      patch(assistantId, (x) => ({ ...x, status: "error", error: message }));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    sendRef.current = send;
  });

  /** Re-send the user message that produced a failed answer. */
  function resend(assistantId: string) {
    const idx = turns.findIndex((x) => x.id === assistantId);
    const userTurn = idx > 0 ? turns[idx - 1] : null;
    if (!userTurn || userTurn.role !== "user") return;
    setTurns((prev) => prev.filter((x) => x.id !== assistantId && x.id !== userTurn.id));
    // Defer until the removal is committed so `busy`/history reflect it.
    setTimeout(() => void send(userTurn.content, { voice: userTurn.viaVoice }), 0);
  }

  function reset() {
    speaker.stop();
    voice.cancel();
    setTurns([]);
    setError(null);
    setInput("");
  }

  async function copy(id: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(id);
      setTimeout(() => setCopied((c) => (c === id ? null : c)), 1600);
    } catch {
      /* clipboard blocked: nothing to do */
    }
  }

  const last = turns[turns.length - 1];
  const examples = [t("examples.one"), t("examples.two"), t("examples.three")];
  const exampleIcons = [Mountain, MapPin, Wheat];
  const timeOf = (at: number) => format.dateTime(new Date(at), { hour: "2-digit", minute: "2-digit" });

  return (
    <div className="flex h-[calc(100dvh-var(--header-h))] flex-col bg-surface-2">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-6 sm:px-6 sm:py-8">
          {turns.length === 0 ? (
            <div className="flex flex-col items-center py-4 text-center sm:py-10">
              <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary text-primary-fg shadow-2">
                <Sparkles className="h-7 w-7" aria-hidden />
              </span>
              <h1 className="mt-6 text-balance text-3xl sm:text-4xl">
                {t("title")}
                <span className="block text-primary">{t("titleLine2")}</span>
              </h1>
              <p className="mt-4 max-w-xl text-base text-muted sm:text-lg">{t("intro")}</p>

              <div className="mt-10 w-full">
                <p className="eyebrow">{t("tryExample")}</p>
                <div className="mt-4 grid gap-3 text-left sm:grid-cols-3">
                  {examples.map((ex, i) => {
                    const Icon = exampleIcons[i] ?? Sparkles;
                    return (
                      <button
                        key={ex}
                        type="button"
                        onClick={() => void send(ex)}
                        className="flex h-full items-start gap-3 rounded-card border border-border bg-surface p-4 text-left shadow-1 transition duration-base hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-2 sm:flex-col"
                      >
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-control bg-primary-soft text-primary">
                          <Icon className="h-4 w-4" aria-hidden />
                        </span>
                        <span className="text-sm leading-relaxed text-text">{ex}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {metaLoading || metaError ? (
                <p className="mt-6 text-xs text-muted">
                  {metaLoading ? t("loadingMeta") : t("backendUnreachable", { error: metaError ?? "" })}
                </p>
              ) : null}
            </div>
          ) : (
            <ol role="log" aria-live="polite" aria-relevant="additions" aria-label={ta("chatLog")} className="space-y-6">
              {turns.map((turn) => {
                const isLast = last?.id === turn.id;
                const role = turn.role === "user" ? t("roles.user") : t("roles.assistant");
                const meta_ = (
                  <span className="text-xs text-muted">
                    <span className="sr-only">{t("timestamp", { role, time: timeOf(turn.at) })}</span>
                    <span aria-hidden>{role} · </span>
                    <time aria-hidden dateTime={new Date(turn.at).toISOString()} className="tabular">
                      {timeOf(turn.at)}
                    </time>
                  </span>
                );
                if (turn.role === "user") {
                  return (
                    <li key={turn.id} className="rise-in flex justify-end">
                      <div className="flex max-w-[85%] flex-col items-end gap-1.5">
                        <div className="whitespace-pre-wrap rounded-2xl rounded-br-md bg-primary px-4 py-3 text-base text-primary-fg shadow-1">
                          {turn.content}
                        </div>
                        <span className="flex items-center gap-1.5">
                          {turn.viaVoice ? <Mic className="h-3 w-3 text-muted" aria-hidden /> : null}
                          {meta_}
                        </span>
                      </div>
                    </li>
                  );
                }
                const working = busy && isLast && turn.status !== "done" && turn.status !== "error";
                const playing = speaker.playing === turn.id;
                const preparing = speaker.loading === turn.id;
                const finished = turn.status === "done" && !!turn.content;
                return (
                  <li key={turn.id} className="rise-in flex gap-3">
                    <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-fg shadow-1">
                      <Leaf className="h-4 w-4" aria-hidden />
                    </span>
                    <div className="min-w-0 flex-1 space-y-3">
                      {turn.content ? (
                        <div className="rounded-2xl rounded-tl-md border border-border bg-surface px-4 py-3.5 shadow-1 sm:px-5">
                          <AssistantMarkdown content={turn.content} />
                          {working && turn.status === "streaming" ? (
                            <Loader2 className="ml-1 inline h-3.5 w-3.5 animate-spin text-muted" aria-hidden />
                          ) : null}
                        </div>
                      ) : null}
                      {working && !turn.content ? (
                        <div
                          className="inline-flex items-center gap-3 rounded-2xl rounded-tl-md border border-border bg-surface px-4 py-3 text-sm text-muted shadow-1"
                          role="status"
                          data-testid="chat-status"
                        >
                          <span aria-hidden className="flex gap-1">
                            {[0, 150, 300].map((d) => (
                              <span key={d} className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary" style={{ animationDelay: `${d}ms` }} />
                            ))}
                          </span>
                          {turn.status === "scoring" ? t("scoring") : t("thinking")}
                        </div>
                      ) : null}
                      {turn.status === "error" ? (
                        <Alert variant="danger" title={t("errorTitle")}>
                          <p lang={/[ሀ-፿]/.test(turn.error ?? "") ? undefined : "en"}>{turn.error ?? t("errorFallback")}</p>
                          <Button variant="outline" size="sm" className="mt-3" onClick={() => resend(turn.id)}>
                            {t("retrySend")}
                          </Button>
                        </Alert>
                      ) : null}
                      {turn.status === "done" ? (
                        <ChatEvidence
                          recommendation={turn.recommendation ?? null}
                          advisory={turn.advisory ?? null}
                          advisoryQuery={turn.advisoryQuery ?? null}
                        />
                      ) : null}
                      {turn.content || turn.status === "error" ? (
                        <div className="flex flex-wrap items-center gap-1.5 pl-1">
                          {finished && caps.output ? (
                            <MessageAction
                              pressed={playing}
                              onClick={() => {
                                if (playing || preparing) speaker.stop();
                                else
                                  void speaker.speak(turn.id, turn.content).then((ok) => {
                                    if (!ok) setError(t("voice.errors.ttsFailed"));
                                  });
                              }}
                              icon={
                                preparing ? (
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                                ) : playing ? (
                                  <Square className="h-3 w-3 fill-current" aria-hidden />
                                ) : (
                                  <Volume2 className="h-3.5 w-3.5" aria-hidden />
                                )
                              }
                              label={preparing ? t("voice.preparing") : playing ? t("voice.stopAudio") : t("voice.listen")}
                            />
                          ) : null}
                          {finished ? (
                            <MessageAction
                              onClick={() => void copy(turn.id, turn.content)}
                              icon={copied === turn.id ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
                              label={copied === turn.id ? t("copied") : t("copy")}
                            />
                          ) : null}
                          <span className="ml-1">{meta_}</span>
                        </div>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ol>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Composer dock */}
      <div className="shrink-0 pb-3 pt-2 sm:pb-4">
        <div className="mx-auto w-full max-w-3xl px-4 sm:px-6">
          {error ? (
            <p className="mb-2 flex items-center gap-2 text-sm text-danger-text" role="alert">
              {error}
              <button type="button" className="underline" onClick={() => setError(null)}>
                {tc("dismiss")}
              </button>
            </p>
          ) : null}
          {turns.length > 0 ? (
            <div className="mb-2 flex justify-end">
              <Button variant="ghost" size="sm" onClick={reset} disabled={busy} className="h-8 rounded-full px-3 text-xs">
                <SquarePen className="h-3.5 w-3.5" aria-hidden />
                {t("newChat")}
              </Button>
            </div>
          ) : null}
          <Composer
            id="chat-input"
            inputRef={inputRef}
            value={input}
            onChange={setInput}
            onSend={() => void send(input)}
            busy={busy}
            placeholder={turns.length === 0 ? t("placeholderHero") : t("placeholder")}
            voice={caps.input ? voice : null}
            readAloud={
              caps.output
                ? {
                    on: autoRead,
                    toggle: () => {
                      if (autoRead) speaker.stop();
                      setAutoRead((v) => !v);
                    },
                  }
                : null
            }
          />
          <p className="mt-2 text-center text-xs text-muted">{t("footnote")}</p>
        </div>
      </div>
    </div>
  );
}

/** A small pill action under an answer (Listen, Copy). */
function MessageAction({
  icon,
  label,
  onClick,
  pressed,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  pressed?: boolean;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium transition-colors duration-base",
        pressed ? "border-primary bg-primary-soft text-primary" : "border-border bg-surface text-muted hover:border-primary/40 hover:text-primary"
      )}
    >
      {icon}
      {label}
    </button>
  );
}

type VoiceControls = ReturnType<typeof useVoiceInput>;

/** Live input level as five bars (server engine) or a gentle pulse (browser engine). */
function LevelMeter({ level }: { level: number }) {
  return (
    <span aria-hidden className="flex h-6 items-center gap-0.5">
      {[0.45, 0.75, 1, 0.75, 0.45].map((m, i) => (
        <span
          key={i}
          className={cn("w-1 rounded-full bg-danger transition-[height] duration-fast", level === 0 && "animate-pulse")}
          style={{ height: `${level === 0 ? 6 + m * 6 : 4 + level * m * 20}px` }}
        />
      ))}
    </span>
  );
}

function Composer({
  id,
  inputRef,
  value,
  onChange,
  onSend,
  busy,
  placeholder,
  voice,
  readAloud,
}: {
  id: string;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  busy: boolean;
  placeholder: string;
  /** Voice controls, or null when no speech-to-text engine works for this language. */
  voice: VoiceControls | null;
  /** "Read every answer aloud" switch, or null when no voice can read this language. */
  readAloud: { on: boolean; toggle: () => void } | null;
}) {
  const t = useTranslations("chat");
  // Grow with the text up to ~6 lines, then scroll.
  useLayoutEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
  }, [value, inputRef]);
  const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  return (
    <form
      className="rounded-2xl border border-border bg-surface p-2 shadow-2 transition-colors duration-base focus-within:border-primary/60"
      onSubmit={(e) => {
        e.preventDefault();
        onSend();
      }}
    >
      {voice?.state === "listening" ? (
        <div className="flex items-center gap-3 px-1 py-0.5" role="status" aria-live="polite">
          <span className="relative flex h-11 w-11 shrink-0 items-center justify-center">
            <span aria-hidden className="absolute inset-0 animate-ping rounded-full bg-danger opacity-25" />
            <span className="relative flex h-11 w-11 items-center justify-center rounded-full bg-danger text-white">
              <Mic className="h-5 w-5" aria-hidden />
            </span>
          </span>
          <div className="min-w-0 flex-1">
            <p className="flex items-center gap-2 text-sm font-medium text-text">
              {t("voice.listening")}
              <span className="tabular text-muted">{mmss(voice.elapsed)}</span>
            </p>
            {voice.interim ? (
              <p className="truncate text-sm text-muted">{voice.interim}</p>
            ) : (
              <span className="flex items-center gap-3">
                <LevelMeter level={voice.level} />
                <span className="truncate text-xs text-muted">{t("voice.autoSend")}</span>
              </span>
            )}
          </div>
          <Button type="button" variant="ghost" size="icon" onClick={voice.cancel} aria-label={t("voice.cancel")} title={t("voice.cancel")} className="h-10 w-10 rounded-full">
            <X className="h-5 w-5" aria-hidden />
          </Button>
          <Button type="button" size="icon" onClick={voice.stop} aria-label={t("voice.stop")} title={t("voice.stop")} className="h-11 w-11 rounded-full">
            <Check className="h-5 w-5" aria-hidden />
          </Button>
        </div>
      ) : voice?.state === "processing" ? (
        <div className="flex h-[3.25rem] items-center gap-3 px-3 text-sm text-muted" role="status">
          <Loader2 className="h-5 w-5 animate-spin text-primary" aria-hidden />
          {t("voice.transcribing")}
        </div>
      ) : (
        <div className="flex items-end gap-1">
          {voice ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => void voice.start()}
              disabled={busy}
              aria-label={t("voice.mic")}
              title={t("voice.mic")}
              className="h-11 w-11 shrink-0 rounded-full text-primary hover:bg-primary-soft"
            >
              <Mic className="h-5 w-5" aria-hidden />
            </Button>
          ) : null}
          {readAloud ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={readAloud.toggle}
              aria-pressed={readAloud.on}
              aria-label={readAloud.on ? t("voice.autoReadOn") : t("voice.autoReadOff")}
              title={readAloud.on ? t("voice.autoReadOn") : t("voice.autoReadOff")}
              className={cn(
                "h-11 w-11 shrink-0 rounded-full",
                readAloud.on ? "bg-primary-soft text-primary" : "text-muted hover:text-primary"
              )}
            >
              {readAloud.on ? <Volume2 className="h-5 w-5" aria-hidden /> : <VolumeX className="h-5 w-5" aria-hidden />}
            </Button>
          ) : null}
          <label className="sr-only" htmlFor={id}>
            {t("message")}
          </label>
          <textarea
            id={id}
            ref={inputRef}
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSend();
              }
            }}
            placeholder={placeholder}
            className="min-h-[2.75rem] min-w-0 flex-1 resize-none bg-transparent px-2 py-2.5 text-base text-text outline-none placeholder:text-muted"
            disabled={busy}
          />
          <Button
            type="submit"
            disabled={busy || !value.trim()}
            loading={busy}
            aria-label={t("ask")}
            className="h-11 shrink-0 rounded-full px-4"
          >
            {!busy ? <Send className="h-4 w-4" aria-hidden /> : null}
            <span className="hidden sm:inline">{t("ask")}</span>
          </Button>
        </div>
      )}
    </form>
  );
}
