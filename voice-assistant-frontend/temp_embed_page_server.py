import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

# Global Variables
PORT = 3019
STATIC_DIR = "/home/mark/projects/14_livekit_server_juno_the_invitation_rag_backend_dev/voice-assistant-frontend/out"
EMBED_EXAMPLE_PATH = "/home/mark/projects/14_livekit_server_juno_the_invitation_rag_backend_dev/voice-assistant-frontend/public/embed-example.html"

app = FastAPI()

# Mount the static files directory from 'out' to ensure assets (JS, CSS, etc.) are available
if os.path.exists(STATIC_DIR):
    app.mount("/_next", StaticFiles(directory=os.path.join(STATIC_DIR, "_next")), name="next_static")
    app.mount("/images", StaticFiles(directory=os.path.join(STATIC_DIR, "images")), name="images")
    app.mount("/fonts", StaticFiles(directory=os.path.join(STATIC_DIR, "fonts")), name="fonts")

@app.get("/")
async def read_index():
    """Serve the embed-example.html as the main index page."""
    if os.path.exists(EMBED_EXAMPLE_PATH):
        return FileResponse(EMBED_EXAMPLE_PATH)
    return {"error": "embed-example.html not found"}

@app.get("/{path:path}")
async def serve_static(path: str):
    """Fallback to serve other static files from the 'out' directory."""
    full_path = os.path.join(STATIC_DIR, path)
    if os.path.isfile(full_path):
        return FileResponse(full_path)
    
    # Handle Next.js style clean URLs
    html_path = full_path + ".html"
    if os.path.isfile(html_path):
        return FileResponse(html_path)
    
    return FileResponse(EMBED_EXAMPLE_PATH)

if __name__ == "__main__":
    print(f"Starting server on http://0.0.0.0:{PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
