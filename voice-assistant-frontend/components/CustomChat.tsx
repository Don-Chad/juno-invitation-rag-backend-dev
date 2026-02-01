"use client";

import { useChat } from "@livekit/components-react";
import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

// Helper component for elegant word-by-word fade in
function StreamingText({ text, isLocal }: { text: string; isLocal: boolean }) {
  const [displayedText, setDisplayedText] = useState("");
  const queueRef = useRef<string[]>([]);
  const processedLengthRef = useRef(0); // Track how much of the source text we've queued
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (isLocal) {
      setDisplayedText(text);
      return;
    }

    // Only queue the part of 'text' we haven't processed yet
    if (text.length > processedLengthRef.current) {
      const newPart = text.slice(processedLengthRef.current);
      const newWords = newPart.split(/(\s+)/).filter(w => w.length > 0);
      queueRef.current = [...queueRef.current, ...newWords];
      processedLengthRef.current = text.length;
    }
  }, [text, isLocal]);

  useEffect(() => {
    if (isLocal) return;

    if (!intervalRef.current) {
      intervalRef.current = setInterval(() => {
        if (queueRef.current.length > 0) {
          const nextWord = queueRef.current.shift();
          setDisplayedText(prev => prev + (nextWord || ""));
        }
      }, 15); // ~3x faster than 40ms (13-15ms)
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [isLocal]);

  if (isLocal) return <>{text}</>;

  const words = displayedText.split(/(\s+)/);
  return (
    <>
      {words.map((word, i) => {
        if (/^\s+$/.test(word)) {
          return <span key={`space-${i}`}>{word}</span>;
        }
        
        return (
          <motion.span
            key={`word-${i}-${word}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.15, ease: "linear" }}
            className="inline-block"
          >
            {word}
          </motion.span>
        );
      })}
    </>
  );
}

// Typing indicator component
function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -10 }}
      className="flex flex-col items-start lk-chat-entry"
    >
      <span className="text-[10px] text-[#B9965B] opacity-70 mb-1 ml-2 font-heading uppercase tracking-widest">
        AVA
      </span>
      <div className="lk-message-body max-w-[85%] sm:max-w-[75%] bg-[#B9965B]/5 rounded-2xl px-4 py-2 flex gap-1.5 items-center min-h-[40px]">
        <motion.span
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ repeat: Infinity, duration: 1.4, times: [0, 0.5, 1], ease: "easeInOut" }}
          className="w-1.5 h-1.5 bg-[#B9965B] rounded-full shadow-[0_0_4px_rgba(185,150,91,0.3)]"
        />
        <motion.span
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ repeat: Infinity, duration: 1.4, times: [0, 0.5, 1], delay: 0.2, ease: "easeInOut" }}
          className="w-1.5 h-1.5 bg-[#B9965B] rounded-full shadow-[0_0_4px_rgba(185,150,91,0.3)]"
        />
        <motion.span
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ repeat: Infinity, duration: 1.4, times: [0, 0.5, 1], delay: 0.4, ease: "easeInOut" }}
          className="w-1.5 h-1.5 bg-[#B9965B] rounded-full shadow-[0_0_4px_rgba(185,150,91,0.3)]"
        />
      </div>
    </motion.div>
  );
}

export function CustomChat() {
  const { send, chatMessages } = useChat();
  const [message, setMessage] = useState("");
  const [isWaiting, setIsWaiting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages update or waiting state changes
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [chatMessages, isWaiting]);

  // Handle waiting state: set to false when a new remote message arrives
  useEffect(() => {
    if (chatMessages.length > 0) {
      const lastMessage = chatMessages[chatMessages.length - 1];
      if (!lastMessage.from?.isLocal) {
        setIsWaiting(false);
      }
    }
  }, [chatMessages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (message.trim()) {
      send(message);
      setMessage("");
      setIsWaiting(true); // Start waiting after sending a message
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setMessage(e.target.value);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  };

  return (
    <div className="flex flex-col h-full w-full">
      {/* Custom Message List */}
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 lk-chat-messages space-y-4"
      >
        <AnimatePresence initial={false}>
          {chatMessages.map((m) => {
            const isLocal = m.from?.isLocal ?? false;
            return (
              <motion.div
                key={m.id}
                initial={{ opacity: 0, x: isLocal ? 10 : -10 }}
                animate={{ opacity: 1, x: 0 }}
                className={`flex flex-col ${isLocal ? "items-end" : "items-start"} lk-chat-entry`}
                data-lk-message-origin={isLocal ? "local" : "remote"}
              >
                {!isLocal && (
                  <span className="text-[10px] text-[#B9965B] opacity-70 mb-1 ml-2 font-heading uppercase tracking-widest">
                    AVA
                  </span>
                )}
                <div className="lk-message-body max-w-[85%] sm:max-w-[75%]">
                  <StreamingText text={m.message} isLocal={isLocal} />
                </div>
              </motion.div>
            );
          })}
          {isWaiting && <TypingIndicator />}
        </AnimatePresence>
      </div>

      {/* Custom Multi-line Input Form */}
      <div className="p-4 border-t border-[#B9965B]/30 relative z-[100] bg-white sm:bg-white/80 backdrop-blur-md pointer-events-auto shadow-[0_-4px_10px_rgba(0,0,0,0.05)]">
        <form onSubmit={handleSubmit} className="flex items-end gap-2 relative z-[110]">
          <textarea
            ref={textareaRef}
            rows={3}
            value={message}
            placeholder="Type a message..."
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            className="lk-chat-form-input flex-1 min-h-[4.5rem] max-h-[12rem] resize-none overflow-y-auto py-3 relative z-[120]"
          />
          <button
            type="submit"
            disabled={!message.trim()}
            className="lk-chat-form-button relative z-[120]"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 256 256"
              fill="currentColor"
            >
              <path d="M231.4,44.34s0,.1,0,.15l-58.2,191.94a15.88,15.88,0,0,1-14,11.51q-.69.06-1.38.06a15.86,15.86,0,0,1-14.42-9.15l-35.71-75.39a4,4,0,0,1,.79-4.54l57.26-57.27a8,8,0,0,0-11.31-11.31L97.08,147.6a4,4,0,0,1-4.54.79l-75-35.53A16.37,16.37,0,0,1,8,97.36,15.89,15.89,0,0,1,19.57,82.84l191.94-58.2.15,0A16,16,0,0,1,231.4,44.34Z"></path>
            </svg>
          </button>
        </form>
      </div>
    </div>
  );
}
