import asyncio
import sys
import os
import firebase_admin
from firebase_admin import credentials, firestore

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def activate_user(email: str):
    print(f"Activating user: {email}")
    
    # Use the service account file
    cred_path = "/home/mark/projects/14_livekit_server_juno_the_invitation_rag_backend_dev/ai-chatbot-v1-645d6-firebase-adminsdk-fbsvc-0b24386fbb.json"
    
    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    
    # Find user by email
    users_ref = db.collection('users')
    query = users_ref.where('email', '==', email.lower()).limit(1).stream()
    
    user_doc = None
    for doc in query:
        user_doc = doc
        break
        
    if user_doc:
        print(f"Found user document: {user_doc.id}")
        doc_ref = users_ref.document(user_doc.id)
        doc_ref.update({
            'subscription': {
                'status': 'active',
                'plan': 'pro_dev',
                'updatedAt': firestore.SERVER_TIMESTAMP
            },
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        # Verwijder het foutieve veld op het hoogste niveau indien aanwezig
        doc_ref.update({
            'subscriptionStatus': firestore.DELETE_FIELD
        })
        print(f"Successfully activated user {email} (standard format)")
    else:
        print(f"No user found with email {email}. Creating a new one...")
        new_doc_ref = users_ref.document()
        new_doc_ref.set({
            'email': email.lower(),
            'createdAt': firestore.SERVER_TIMESTAMP,
            'subscription': {
                'status': 'active',
                'plan': 'pro_dev',
                'updatedAt': firestore.SERVER_TIMESTAMP
            },
            'updatedAt': firestore.SERVER_TIMESTAMP
        })
        print(f"Created and activated new user document for {email} (standard format)")
        print(f"Created and activated new user document for {email}")

if __name__ == "__main__":
    email = "info@makecontact.io"
    asyncio.run(activate_user(email))
