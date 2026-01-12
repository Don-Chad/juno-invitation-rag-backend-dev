import type { AppConfig } from './lib/types';

export const APP_CONFIG_DEFAULTS: AppConfig = {
  supportsChatInput: true,
  supportsVideoInput: false, // Disabled for chat-only mode
  supportsScreenShare: false, // Disabled for chat-only mode
  isPreConnectBufferEnabled: false, // Disabled - no audio pre-buffering needed for chat
};
