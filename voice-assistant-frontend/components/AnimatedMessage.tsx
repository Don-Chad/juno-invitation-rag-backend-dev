"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";

interface AnimatedMessageProps {
  text: string;
  isAssistant: boolean;
}

export function AnimatedMessage({ text, isAssistant }: AnimatedMessageProps) {
  const [displayedText, setDisplayedText] = useState("");
  const [isComplete, setIsComplete] = useState(false);

  useEffect(() => {
    if (!isAssistant) {
      setDisplayedText(text);
      setIsComplete(true);
      return;
    }

    // Reset for new messages
    setDisplayedText("");
    setIsComplete(false);
    
    let currentIndex = 0;
    const interval = setInterval(() => {
      if (currentIndex <= text.length) {
        setDisplayedText(text.slice(0, currentIndex));
        currentIndex++;
      } else {
        setIsComplete(true);
        clearInterval(interval);
      }
    }, 20); // Adjust speed here (lower = faster)

    return () => clearInterval(interval);
  }, [text, isAssistant]);

  if (!isAssistant) {
    return <span>{text}</span>;
  }

  return (
    <motion.span
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      {displayedText.split("").map((char, index) => {
        const totalChars = displayedText.length;
        const goldThreshold = Math.min(15, totalChars * 0.3); // First 30% or 15 chars max
        const isGolden = index < goldThreshold && !isComplete;
        
        return (
          <motion.span
            key={`${index}-${char}`}
            initial={{ color: isGolden ? "#B9965B" : "#000000" }}
            animate={{ 
              color: isComplete || index >= goldThreshold ? "#000000" : "#B9965B"
            }}
            transition={{ 
              duration: 0.8,
              delay: index * 0.02,
              ease: "easeOut"
            }}
          >
            {char}
          </motion.span>
        );
      })}
    </motion.span>
  );
}

