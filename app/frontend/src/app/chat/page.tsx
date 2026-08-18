"use client";

import { useEffect, useState } from "react";
import { ChatPanel } from "@/components/chat-panel";

export default function ChatPage() {
  const [seed, setSeed] = useState<string | null>(null);

  useEffect(() => {
    const s = sessionStorage.getItem("agro-seed-message");
    if (s) {
      sessionStorage.removeItem("agro-seed-message");
      setSeed(s);
    }
  }, []);

  return <ChatPanel seedMessage={seed} />;
}
