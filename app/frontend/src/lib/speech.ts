"use client";

/**
 * Chat voice (U6): speech-to-text for the question, text-to-speech for the
 * answer, in English, Amharic and Afaan Oromoo.
 *
 * Two engines per direction, chosen once per language:
 *  - "server": POST /speech/* (OpenAI audio models), when /speech/status says
 *    the configured models are reachable;
 *  - "browser": the Web Speech API (SpeechRecognition / speechSynthesis), when
 *    the browser offers it for that language.
 * When neither works the control is simply not shown (degrade, never break).
 * Spoken answers are the assistant's own text with formatting removed; no
 * number or word is changed (CLAUDE.md doctrine 1).
 */
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { fetchSpeechStatus, synthesizeSpeech, transcribeAudio, type SpeechStatus } from "./api";
import type { ApiLanguage } from "./types";

export type SpeechEngine = "server" | "browser";

/** BCP-47 tags for the browser engines. */
export const SPEECH_LANG: Record<ApiLanguage, string> = { en: "en-US", am: "am-ET", om: "om-ET" };

// ----------------------------------------------------------- text for speech
const CITATION = /\[(?:G|W)?\d+(?:\s*[,–-]\s*(?:G|W)?\d+)*\]/g;
const LINK = /\[([^\]]+)\]\([^)]+\)/g;
const URL_RE = /https?:\/\/\S+/g;
const MD_MARKS = /(\*\*|__|\*|_|`+|^#{1,6}\s*|^>\s*)/gm;
const BULLET = /^\s*(?:[-*+]|\d+[.)])\s+/gm;

/** Mirror of the backend's clean_for_speech: formatting out, words and numbers kept. */
export function speakableText(markdown: string): string {
  const lines = markdown
    .replace(LINK, "$1")
    .replace(URL_RE, "")
    .replace(CITATION, "")
    .replace(BULLET, "")
    .replace(MD_MARKS, "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  return lines
    .map((l) => (/[.?!።]$/.test(l) ? l : `${l.replace(/[:;,]+$/, "")}.`))
    .join(" ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .replace(/\s{2,}/g, " ")
    .trim();
}

/**
 * Split speakable text into sentence groups of at most `limit` characters for
 * incremental server synthesis (a sentence longer than the limit stays whole).
 */
export function speechSegments(text: string, limit = 220): string[] {
  const sentences = text.split(/(?<=[.!?።])\s+/).map((s) => s.trim()).filter(Boolean);
  const out: string[] = [];
  for (const s of sentences) {
    const last = out[out.length - 1];
    if (last && last.length + 1 + s.length <= limit) out[out.length - 1] = `${last} ${s}`;
    else out.push(s);
  }
  return out;
}

// ---------------------------------------------------------- browser support
interface RecognitionResult {
  isFinal: boolean;
  0: { transcript: string };
}
interface RecognitionEvent {
  resultIndex: number;
  results: ArrayLike<RecognitionResult>;
}
interface Recognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: RecognitionEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type RecognitionCtor = new () => Recognition;

function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** speechSynthesis voices load asynchronously; expose them as an external store. */
function subscribeVoices(cb: () => void) {
  if (typeof window === "undefined" || !window.speechSynthesis) return () => {};
  window.speechSynthesis.addEventListener("voiceschanged", cb);
  return () => window.speechSynthesis.removeEventListener("voiceschanged", cb);
}
let voiceSnapshot: { key: string; voices: SpeechSynthesisVoice[] } = { key: "", voices: [] };
function getVoices(): SpeechSynthesisVoice[] {
  if (typeof window === "undefined" || !window.speechSynthesis) return voiceSnapshot.voices;
  const voices = window.speechSynthesis.getVoices();
  const key = voices.map((v) => v.voiceURI).join("|");
  if (key !== voiceSnapshot.key) voiceSnapshot = { key, voices };
  return voiceSnapshot.voices;
}
const NO_VOICES: SpeechSynthesisVoice[] = [];
const getVoicesServer = (): SpeechSynthesisVoice[] => NO_VOICES;

function voiceFor(voices: SpeechSynthesisVoice[], lang: ApiLanguage): SpeechSynthesisVoice | null {
  const prefix = lang.toLowerCase();
  const matches = voices.filter((v) => v.lang.toLowerCase().startsWith(prefix));
  return matches.find((v) => /natural|neural|google/i.test(v.name)) ?? matches[0] ?? null;
}

const noopSubscribe = () => () => {};

// --------------------------------------------------------- engine selection
let statusPromise: Promise<SpeechStatus> | null = null;
const loadStatus = () => (statusPromise ??= fetchSpeechStatus());

export interface SpeechCapabilities {
  /** Engine for voice input in this language, or null (no mic shown). */
  input: SpeechEngine | null;
  /** Engine for reading answers aloud in this language, or null (no Listen shown). */
  output: SpeechEngine | null;
  voice: SpeechSynthesisVoice | null;
}

export function useSpeechCapabilities(lang: ApiLanguage): SpeechCapabilities {
  const [server, setServer] = useState<SpeechStatus | null>(null);
  useEffect(() => {
    let live = true;
    void loadStatus().then((s) => live && setServer(s));
    return () => {
      live = false;
    };
  }, []);
  const voices = useSyncExternalStore(subscribeVoices, getVoices, getVoicesServer);
  // Browser support is unknown on the server: report nothing until hydrated.
  const mounted = useSyncExternalStore(noopSubscribe, () => true, () => false);
  if (!mounted) return { input: null, output: null, voice: null };
  const voice = voiceFor(voices, lang);
  const canRecord = typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";
  return {
    input: server?.stt[lang] && canRecord ? "server" : recognitionCtor() ? "browser" : null,
    output: server?.tts[lang] ? "server" : voice ? "browser" : null,
    voice,
  };
}

// --------------------------------------------------------------- voice input
export type VoiceState = "idle" | "listening" | "processing";

/** End-of-speech detection for the server engine (input level 0..1). */
const SPEECH_LEVEL = 0.12;
const SILENCE_MS = 1600;
const NO_SPEECH_MS = 8000;
const MAX_MS = 60_000;
export type VoiceError = "denied" | "no-speech" | "unsupported-language" | "failed";

/**
 * Records one spoken question and hands back its text. Exposes a 0..1 input
 * level (server engine) and the elapsed seconds for the recording UI.
 */
export function useVoiceInput({
  lang,
  engine,
  onText,
  onError,
}: {
  lang: ApiLanguage;
  engine: SpeechEngine | null;
  onText: (text: string) => void;
  onError: (e: VoiceError) => void;
}) {
  const [state, setState] = useState<VoiceState>("idle");
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [interim, setInterim] = useState("");
  const cleanup = useRef<(() => void) | null>(null);
  const finish = useRef<((send: boolean) => void) | null>(null);

  const reset = useCallback(() => {
    cleanup.current?.();
    cleanup.current = null;
    finish.current = null;
    setLevel(0);
    setElapsed(0);
    setInterim("");
  }, []);

  useEffect(() => reset, [reset]);

  const start = useCallback(async () => {
    if (!engine || state !== "idle") return;
    const startedAt = Date.now();
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 250);

    if (engine === "browser") {
      const Ctor = recognitionCtor();
      if (!Ctor) return onError("failed");
      const rec = new Ctor();
      rec.lang = SPEECH_LANG[lang];
      rec.interimResults = true;
      // Hands-free: the browser ends the session itself when the speaker pauses.
      rec.continuous = false;
      let finalText = "";
      let lastInterim = "";
      let keep = true;
      rec.onresult = (e) => {
        let live = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const r = e.results[i];
          if (r.isFinal) finalText += `${r[0].transcript} `;
          else live += r[0].transcript;
        }
        lastInterim = live;
        setInterim(`${finalText}${live}`.trim());
      };
      rec.onerror = (e) => {
        keep = false;
        onError(
          e.error === "not-allowed" || e.error === "service-not-allowed"
            ? "denied"
            : e.error === "no-speech"
              ? "no-speech"
              : e.error === "language-not-supported"
                ? "unsupported-language"
                : "failed"
        );
      };
      rec.onend = () => {
        window.clearInterval(timer);
        // "Done" pressed mid-phrase: keep the words heard so far.
        const text = (finalText || lastInterim).trim();
        reset();
        setState("idle");
        if (keep && text) onText(text);
        else if (keep) onError("no-speech");
      };
      cleanup.current = () => window.clearInterval(timer);
      finish.current = (send) => {
        keep = keep && send;
        if (send) rec.stop();
        else rec.abort();
      };
      setState("listening");
      try {
        rec.start();
      } catch {
        window.clearInterval(timer);
        reset();
        setState("idle");
        onError("failed");
      }
      return;
    }

    // Server engine: record with MediaRecorder, meter the level, upload on stop.
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      window.clearInterval(timer);
      return onError("denied");
    }
    const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"].find((m) => MediaRecorder.isTypeSupported(m));
    const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks: Blob[] = [];
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);

    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const buf = new Uint8Array(analyser.frequencyBinCount);
    let raf = 0;
    // Hands-free end of speech: once the user has spoken, a pause of
    // SILENCE_MS ends the recording; nothing heard within NO_SPEECH_MS, or a
    // recording longer than MAX_MS, ends it too.
    let heard = false;
    let lastLoud = performance.now();
    const began = lastLoud;
    const tick = () => {
      analyser.getByteTimeDomainData(buf);
      let peak = 0;
      for (const v of buf) peak = Math.max(peak, Math.abs(v - 128));
      const lvl = Math.min(1, peak / 64);
      setLevel(lvl);
      const now = performance.now();
      if (lvl > SPEECH_LEVEL) {
        heard = true;
        lastLoud = now;
      }
      const ended =
        (heard && now - lastLoud > SILENCE_MS) || (!heard && now - began > NO_SPEECH_MS) || now - began > MAX_MS;
      if (ended && recorder.state === "recording") {
        finish.current?.(true);
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    cleanup.current = () => {
      window.clearInterval(timer);
      cancelAnimationFrame(raf);
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
    };
    let send = true;
    recorder.onstop = async () => {
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      reset();
      if (!send) return setState("idle");
      if (blob.size < 1200) {
        setState("idle");
        return onError("no-speech");
      }
      setState("processing");
      try {
        const text = (await transcribeAudio(blob, lang)).trim();
        if (text) onText(text);
        else onError("no-speech");
      } catch {
        onError("failed");
      } finally {
        setState("idle");
      }
    };
    finish.current = (s) => {
      send = s;
      recorder.stop();
    };
    recorder.start();
    setState("listening");
  }, [engine, lang, onError, onText, reset, state]);

  const stop = useCallback(() => finish.current?.(true), []);
  const cancel = useCallback(() => finish.current?.(false), []);

  return { state, level, elapsed, interim, start, stop, cancel };
}

// -------------------------------------------------------------- voice output
/** One speaker for the whole chat: starting an answer stops the previous one. */
export function useSpeaker({
  lang,
  engine,
  voice,
}: {
  lang: ApiLanguage;
  engine: SpeechEngine | null;
  voice: SpeechSynthesisVoice | null;
}) {
  const [playing, setPlaying] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const abort = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    abort.current?.abort();
    abort.current = null;
    if (audio.current) {
      audio.current.pause();
      URL.revokeObjectURL(audio.current.src);
      audio.current = null;
    }
    if (typeof window !== "undefined") window.speechSynthesis?.cancel();
    setPlaying(null);
    setLoading(null);
  }, []);

  useEffect(() => stop, [stop]);

  const speak = useCallback(
    async (id: string, markdown: string): Promise<boolean> => {
      stop();
      const text = speakableText(markdown);
      if (!engine || !text) return false;
      if (engine === "browser") {
        const u = new SpeechSynthesisUtterance(text);
        u.lang = SPEECH_LANG[lang];
        if (voice) u.voice = voice;
        u.rate = 0.98;
        u.onend = () => setPlaying((p) => (p === id ? null : p));
        u.onerror = () => setPlaying((p) => (p === id ? null : p));
        setPlaying(id);
        window.speechSynthesis.speak(u);
        return true;
      }
      // Server voice, sentence by sentence: the first piece plays as soon as it
      // is ready while the next one is synthesized (a long answer would
      // otherwise wait for the whole text).
      const ctl = new AbortController();
      abort.current = ctl;
      setLoading(id);
      const segments = speechSegments(text);
      const fetchSegment = (i: number) => {
        const p = synthesizeSpeech(segments[i], lang, ctl.signal);
        p.catch(() => {}); // a prefetch abandoned by stop() must not surface as unhandled
        return p;
      };
      try {
        let next = fetchSegment(0);
        for (let i = 0; i < segments.length; i++) {
          const blob = await next;
          if (ctl.signal.aborted) return false;
          if (i + 1 < segments.length) next = fetchSegment(i + 1);
          const el = new Audio(URL.createObjectURL(blob));
          audio.current = el;
          const finished = new Promise<void>((resolve) => {
            el.onended = () => resolve();
            el.onpause = () => resolve();
            el.onerror = () => resolve();
          });
          await el.play();
          if (i === 0) {
            setLoading(null);
            setPlaying(id);
          }
          await finished;
          URL.revokeObjectURL(el.src);
          if (ctl.signal.aborted) return true;
        }
        setPlaying((p) => (p === id ? null : p));
        return true;
      } catch {
        if (!ctl.signal.aborted) {
          setLoading(null);
          setPlaying(null);
        }
        return false;
      }
    },
    [engine, lang, stop, voice]
  );

  return { playing, loading, speak, stop };
}
