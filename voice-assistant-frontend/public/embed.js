/**
 * AVA Voice Assistant Embed Script
 * 
 * Usage:
 * <script src="https://your-domain.com/embed.js" 
 *         data-iframe-src="https://your-domain.com/embed"
 *         data-width="100%"
 *         data-height="600px"></script>
 * 
 * Or programmatically:
 * AVAEmbed.init({
 *   iframeSrc: 'https://your-domain.com/embed',
 *   container: document.getElementById('ava-container'),
 *   width: '100%',
 *   height: '600px'
 * });
 */

(function() {
  'use strict';

  // Default configuration
  const DEFAULTS = {
    width: '100%',
    height: '600px',
    minHeight: '400px',
    border: 'none',
    borderRadius: '12px',
    boxShadow: '0 4px 20px rgba(0, 0, 0, 0.15)'
  };

  /**
   * Create and inject the iframe
   */
  function createIframe(config) {
    const container = config.container || createContainer();
    
    // Create iframe element
    const iframe = document.createElement('iframe');
    iframe.src = config.iframeSrc;
    iframe.width = config.width || DEFAULTS.width;
    iframe.height = config.height || DEFAULTS.height;
    iframe.style.border = config.border || DEFAULTS.border;
    iframe.style.borderRadius = config.borderRadius || DEFAULTS.borderRadius;
    iframe.style.boxShadow = config.boxShadow || DEFAULTS.boxShadow;
    iframe.style.minHeight = config.minHeight || DEFAULTS.minHeight;
    iframe.setAttribute('allow', 'microphone; camera; autoplay');
    iframe.setAttribute('sandbox', 'allow-same-origin allow-scripts allow-popups allow-forms allow-popups-to-escape-sandbox');
    iframe.setAttribute('loading', 'lazy');
    iframe.setAttribute('title', 'AVA Voice Assistant');
    
    // Add responsive styles
    iframe.style.maxWidth = '100%';
    iframe.style.display = 'block';
    
    container.appendChild(iframe);
    
    return { iframe, container };
  }

  /**
   * Create a default container if none provided
   */
  function createContainer() {
    const container = document.createElement('div');
    container.id = 'ava-embed-container-' + Date.now();
    container.style.width = '100%';
    container.style.position = 'relative';
    
    // Insert after the script tag or at end of body
    const currentScript = document.currentScript;
    if (currentScript && currentScript.parentNode) {
      currentScript.parentNode.insertBefore(container, currentScript.nextSibling);
    } else {
      document.body.appendChild(container);
    }
    
    return container;
  }

  /**
   * Get configuration from data attributes
   */
  function getConfigFromDataAttributes() {
    const script = document.currentScript;
    if (!script) return null;
    
    return {
      iframeSrc: script.getAttribute('data-iframe-src'),
      width: script.getAttribute('data-width'),
      height: script.getAttribute('data-height'),
      border: script.getAttribute('data-border'),
      borderRadius: script.getAttribute('data-border-radius'),
      boxShadow: script.getAttribute('data-box-shadow'),
      minHeight: script.getAttribute('data-min-height')
    };
  }

  /**
   * Initialize the embed
   */
  function init(userConfig) {
    const config = { ...DEFAULTS, ...userConfig };
    
    if (!config.iframeSrc) {
      console.error('AVA Embed: iframeSrc is required');
      return null;
    }
    
    return createIframe(config);
  }

  /**
   * Auto-initialize if data attributes are present
   */
  function autoInit() {
    const config = getConfigFromDataAttributes();
    if (config && config.iframeSrc) {
      // Wait for DOM to be ready
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => init(config));
      } else {
        init(config);
      }
    }
  }

  // Expose API
  window.AVAEmbed = {
    init,
    version: '1.0.0'
  };

  // Auto-initialize
  autoInit();
})();
