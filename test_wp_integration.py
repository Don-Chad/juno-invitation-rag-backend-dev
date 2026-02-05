import requests
import json
import time
from datetime import datetime

# CONFIGURATION
# Update these to match your local or production environment
BACKEND_URL = "http://localhost:3011"
API_KEY = "test_secret_key"  # Must match what you put in WP settings
SITE_ID = "juno_prod"
TEST_EMAIL = "mark@dopamine.amsterdam"

def log_test(name, success, message=""):
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status} [{name}] {message}")

def test_webhook_purchase():
    print(f"\n--- Testing Webhook: New Purchase ---")
    payload = {
        "eventType": "user_created",
        "siteId": SITE_ID,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": {
            "wpUserId": "12345",
            "email": TEST_EMAIL,
            "displayName": "Mark Test",
            "wpOrderId": "999",
            "wpSubscriptionId": "sub_888",
            "subscriptionStatus": "active",
            "plan": "basic",
            "startedAt": datetime.now().isoformat(),
            "expiresAt": None,
            "isTrial": False
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-AVA-API-Key": API_KEY,
        "X-AVA-Site-ID": SITE_ID
    }
    
    try:
        response = requests.post(f"{BACKEND_URL}/api/webhook/subscription", json=payload, headers=headers)
        if response.status_code == 200:
            log_test("Purchase Webhook", True, f"Server accepted webhook for {TEST_EMAIL}")
            return True
        else:
            log_test("Purchase Webhook", False, f"Server returned {response.status_code}: {response.text}")
            return False
    except Exception as e:
        log_test("Purchase Webhook", False, str(e))
        return False

def test_webhook_email_change():
    print(f"\n--- Testing Webhook: Email Change (Security Wipe) ---")
    new_email = "mark@dopamine.amsterdam"
    payload = {
        "eventType": "email_changed",
        "siteId": SITE_ID,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": {
            "wpUserId": "12345",
            "oldEmail": TEST_EMAIL,
            "newEmail": new_email,
            "displayName": "Mark New"
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-AVA-API-Key": API_KEY,
        "X-AVA-Site-ID": SITE_ID
    }
    
    try:
        response = requests.post(f"{BACKEND_URL}/api/webhook/subscription", json=payload, headers=headers)
        if response.status_code == 200:
            log_test("Email Change Webhook", True, f"Server accepted change from {TEST_EMAIL} to {new_email}")
            print("     (Note: This should have triggered a history wipe and key burn in Firestore)")
            return True
        else:
            log_test("Email Change Webhook", False, f"Server returned {response.status_code}: {response.text}")
            return False
    except Exception as e:
        log_test("Email Change Webhook", False, str(e))
        return False

def test_token_server_health():
    print(f"\n--- Testing Token Server Health ---")
    try:
        response = requests.get(f"{BACKEND_URL}/healthz")
        if response.status_code == 200:
            log_test("Health Check", True, "Token server is running")
            return True
        else:
            log_test("Health Check", False, f"Status {response.status_code}")
            return False
    except:
        log_test("Health Check", False, "Could not connect to token server. Is it running on port 3011?")
        return False

if __name__ == "__main__":
    print("==========================================")
    print("AVA WORDPRESS INTEGRATION TEST SUITE")
    print("==========================================")
    
    if test_token_server_health():
        test_webhook_purchase()
        time.sleep(1) # Small delay
        test_webhook_email_change()
    
    print("\n==========================================")
    print("TESTING COMPLETE")
    print("Check your Firestore 'users' and 'subscriptionEvents' collections to verify data.")
