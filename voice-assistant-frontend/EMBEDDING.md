# AVA Voice Assistant - Embedding Guide

This guide explains how to embed the AVA Voice Assistant with Firebase Google Authentication on external websites.

## Overview

The embeddable version is available at `/embed` route and provides the full AVA interface including:
- Google OAuth authentication via Firebase
- LiveKit voice/chat connection
- The complete UI with background, chat interface, and controls

## Important: Firebase Auth in Cross-Origin Iframes

When embedding on a **different domain**, there are some browser restrictions to be aware of:

### The Challenge
Google OAuth popup authentication may be blocked by some browsers when the page is inside a cross-origin iframe. This is a security feature of modern browsers.

### Solutions

#### Option 1: Direct Iframe Embedding (Recommended for Same Domain/Subdomain)
If your parent site and AVA frontend are on the same domain or subdomain:

```html
<iframe 
  src="https://your-ava-domain.com/embed"
  width="100%"
  height="600px"
  style="border: none; border-radius: 12px;"
  allow="microphone; camera; autoplay"
  sandbox="allow-same-origin allow-scripts allow-popups allow-forms allow-popups-to-escape-sandbox">
</iframe>
```

#### Option 2: Using the Embed Script
Include the embed script on your page:

```html
<script 
  src="https://your-ava-domain.com/embed.js"
  data-iframe-src="https://your-ava-domain.com/embed"
  data-width="100%"
  data-height="600px">
</script>
```

#### Option 3: Programmatic Initialization
```html
<div id="ava-container"></div>
<script src="https://your-ava-domain.com/embed.js"></script>
<script>
  AVAEmbed.init({
    iframeSrc: 'https://your-ava-domain.com/embed',
    container: document.getElementById('ava-container'),
    width: '100%',
    height: '600px',
    borderRadius: '16px'
  });
</script>
```

#### Option 4: Popup Window (Best for Cross-Domain)
For completely different domains, open AVA in a popup instead of an iframe:

```javascript
function openAVAChat() {
  const width = 450;
  const height = 700;
  const left = (window.innerWidth - width) / 2;
  const top = (window.innerHeight - height) / 2;
  
  window.open(
    'https://your-ava-domain.com/embed',
    'AVAChat',
    `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=no`
  );
}

// Use a button to trigger
<button onclick="openAVAChat()">Chat with AVA</button>
```

## Configuration Options

### Embed Script Data Attributes

| Attribute | Description | Default |
|-----------|-------------|---------|
| `data-iframe-src` | URL to the embed page | Required |
| `data-width` | Iframe width | `100%` |
| `data-height` | Iframe height | `600px` |
| `data-min-height` | Minimum height | `400px` |
| `data-border` | Border style | `none` |
| `data-border-radius` | Border radius | `12px` |
| `data-box-shadow` | Box shadow | `0 4px 20px rgba(0,0,0,0.15)` |

### JavaScript API

```javascript
// Initialize with options
const embed = AVAEmbed.init({
  iframeSrc: 'https://your-ava-domain.com/embed',
  container: document.getElementById('container'), // Optional
  width: '100%',
  height: '700px',
  minHeight: '500px',
  border: '1px solid #ddd',
  borderRadius: '16px',
  boxShadow: '0 8px 30px rgba(0,0,0,0.2)'
});

// The init function returns:
// {
//   iframe: HTMLIFrameElement,
//   container: HTMLElement
// }
```

## Security Considerations

### Content Security Policy
The embed route includes headers to allow iframe embedding:
- `X-Frame-Options: ALLOWALL`
- `Content-Security-Policy: frame-ancestors *;`

### Sandbox Permissions
The iframe uses the following sandbox permissions:
- `allow-same-origin`: Required for Firebase auth
- `allow-scripts`: Required for JavaScript execution
- `allow-popups`: Required for Google OAuth popup
- `allow-forms`: Required for form submissions
- `allow-popups-to-escape-sandbox`: Allows OAuth popup to escape sandbox

### Firebase Configuration
Ensure your Firebase project allows the parent domain:
1. Go to Firebase Console → Authentication → Settings → Authorized domains
2. Add the parent website domain

## Browser Compatibility

| Browser | Iframe + Google Auth | Notes |
|---------|---------------------|-------|
| Chrome | ✅ Supported | Works with COOP headers |
| Firefox | ✅ Supported | Works with COOP headers |
| Safari | ⚠️ Limited | May block third-party cookies |
| Edge | ✅ Supported | Works with COOP headers |

## Troubleshooting

### "Popup blocked" error
The browser blocked the Google OAuth popup. Solutions:
1. Use Option 4 (popup window) instead of iframe
2. Ask users to allow popups for your domain
3. Use a same-domain/subdomain setup

### "Unable to process request" error
Check Firebase authorized domains include the parent website domain.

### Blank iframe
Check browser console for CORS errors. Ensure the embed route headers are properly configured.

### Authentication loop
Clear browser cookies and cache. Check that `Cross-Origin-Opener-Policy` header is set to `same-origin-allow-popups`.

## Example Implementation

### Basic HTML Page
```html
<!DOCTYPE html>
<html>
<head>
  <title>My Website with AVA</title>
  <style>
    .ava-wrapper {
      max-width: 800px;
      margin: 0 auto;
      padding: 20px;
    }
  </style>
</head>
<body>
  <h1>Welcome to My Website</h1>
  
  <div class="ava-wrapper">
    <h2>Chat with AVA</h2>
    <script 
      src="https://your-ava-domain.com/embed.js"
      data-iframe-src="https://your-ava-domain.com/embed"
      data-width="100%"
      data-height="700px">
    </script>
  </div>
</body>
</html>
```

### React Component
```jsx
import { useEffect, useRef } from 'react';

function AVAEmbed({ src, width = '100%', height = '600px' }) {
  const containerRef = useRef(null);

  useEffect(() => {
    if (window.AVAEmbed && containerRef.current) {
      window.AVAEmbed.init({
        iframeSrc: src,
        container: containerRef.current,
        width,
        height
      });
    }
  }, [src, width, height]);

  return <div ref={containerRef} />;
}

// Usage
<AVAEmbed 
  src="https://your-ava-domain.com/embed"
  width="100%"
  height="700px"
/>
```

## Support

For issues or questions about embedding AVA, please refer to the project documentation or contact the development team.