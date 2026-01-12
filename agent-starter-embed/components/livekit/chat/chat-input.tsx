import { useEffect, useRef, useState } from 'react';
import { PaperPlaneRightIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface ChatInputProps extends React.HTMLAttributes<HTMLFormElement> {
  onSend?: (message: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, className, disabled, ...props }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [message, setMessage] = useState<string>('');

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    props.onSubmit?.(e);
    onSend?.(message);
    setMessage('');
    // Reset height after sending
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Submit on Enter without Shift
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!isDisabled) {
        handleSubmit(e as any);
      }
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setMessage(e.target.value);
    // Auto-resize textarea
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  };

  const isDisabled = disabled || message.trim().length === 0;

  useEffect(() => {
    if (disabled) {
      return;
    }
    // when not disabled refocus on textarea
    textareaRef.current?.focus();
  }, [disabled]);

  return (
    <form
      {...props}
      onSubmit={handleSubmit}
      className={cn('flex items-end gap-2 rounded-md pl-1 text-sm', className)}
    >
      <textarea
        autoFocus
        ref={textareaRef}
        rows={3}
        value={message}
        disabled={disabled}
        placeholder="Type something... (Shift+Enter for new line)"
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        className="min-h-[4.5rem] max-h-[12rem] shrink-1 grow-1 pl-2 py-2 resize-none overflow-y-auto focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
      />
      <Button
        size="icon"
        type="submit"
        variant={isDisabled ? 'secondary' : 'primary'}
        disabled={isDisabled}
        className="mb-1"
      >
        <PaperPlaneRightIcon weight="bold" />
      </Button>
    </form>
  );
}
