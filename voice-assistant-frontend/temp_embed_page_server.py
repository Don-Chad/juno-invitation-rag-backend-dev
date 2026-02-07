"""
Simulates a CUSTOMER'S WEBSITE that embeds the AVA voice assistant via iframe.

This server does NOT serve the AVA frontend itself. It only serves an HTML page
that contains an <iframe> pointing to the PRODUCTION AVA domain
(https://the-invitation-2.makecontact.io/embed).

This is the correct way to test the embed flow locally:
  - This server = the customer site (e.g., junoburger.com)
  - The iframe inside points to the real AVA frontend on Cloudflare
  - Firebase auth, cookies, BroadcastChannel all happen on the AVA domain

DO NOT serve the out/ directory from here. The out/ directory is a static export
meant for Cloudflare deployment. Serving it locally on a different port causes
domain mismatches with Firebase authorized domains and cookie origins.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
import os

# Global Variables
PORT = 3019
EMBED_EXAMPLE_PATH = os.path.join(
    os.path.dirname(__file__),
    "public",
    "embed-example.html"
)

app = FastAPI()

@app.get("/")
async def read_index():
    """Serve the embed-example.html — simulates a customer's website with the AVA iframe."""
    if os.path.exists(EMBED_EXAMPLE_PATH):
        return FileResponse(EMBED_EXAMPLE_PATH)
    return {"error": "embed-example.html not found", "expected_path": EMBED_EXAMPLE_PATH}

if __name__ == "__main__":
    print(f"=== AVA Embed Test Server (simulates customer site) ===")
    print(f"Open http://localhost:{PORT} to see the embedded AVA assistant")
    print(f"The iframe inside points to the PRODUCTION AVA domain.")
    print(f"=========================================================")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
