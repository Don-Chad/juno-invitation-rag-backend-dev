import asyncio
import sys
import os
import firebase_admin
from firebase_admin import credentials, firestore

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def approve_sites():
    print("Approving sites in Firestore...")
    
    # Use the service account file
    cred_path = "/home/mark/projects/14_livekit_server_juno_the_invitation_rag_backend_dev/ai-chatbot-v1-645d6-firebase-adminsdk-fbsvc-0b24386fbb.json"
    
    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    
    sites = [
        {"id": "juno_prod", "origin": "https://junoburger.com", "allowed": True},
        {"id": "default", "origin": "*", "allowed": True}
    ]
    
    for site in sites:
        site_id = site["id"]
        print(f"Processing site: {site_id}")
        doc_ref = db.collection('approvedSites').document(site_id)
        doc_ref.set({
            "siteId": site_id,
            "origin": site["origin"],
            "allowed": site["allowed"],
            "updatedAt": firestore.SERVER_TIMESTAMP
        })
        print(f"  ✓ Site {site_id} approved.")

if __name__ == "__main__":
    asyncio.run(approve_sites())
