#!/usr/bin/env python3
"""
Test script for Firebase User Manager

This script allows you to:
1. Test user creation/retrieval
2. Test message storage
3. Test chat history loading
4. Visualize the data in Firebase

Usage:
    python benchmark_tools/test_firebase_user_manager.py
    
    # Or with specific test user:
    python benchmark_tools/test_firebase_user_manager.py --user test_user_123
"""

import asyncio
import sys
import os
import argparse
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from custom_components.firebase_user_manager import get_firebase_manager, UserSession


async def test_user_session(user_id: str):
    """Test user session creation and retrieval"""
    print("\n" + "="*60)
    print("TEST 1: User Session Management")
    print("="*60)
    
    mgr = get_firebase_manager()
    
    # Create or get user
    print(f"\n[1.1] Getting/creating user: {user_id}")
    user = await mgr.get_or_create_user(user_id, display_name=f"Test User {user_id}")
    
    print(f"  ✓ User ID: {user.user_id}")
    print(f"  ✓ Display Name: {user.display_name}")
    print(f"  ✓ Created At: {user.created_at}")
    print(f"  ✓ Last Active: {user.last_active}")
    print(f"  ✓ Authenticated: {user.is_authenticated}")
    
    # Update settings
    print(f"\n[1.2] Updating user settings...")
    settings = {
        "theme": "dark",
        "language": "en",
        "notifications": True,
        "test_timestamp": datetime.utcnow().isoformat()
    }
    success = await mgr.update_user_settings(user_id, settings)
    print(f"  ✓ Settings updated: {success}")
    
    # Retrieve again to verify
    print(f"\n[1.3] Verifying user data...")
    user = await mgr.get_or_create_user(user_id)
    print(f"  ✓ User still exists: {user.user_id}")
    
    return user


async def test_message_storage(user_id: str):
    """Test storing chat messages"""
    print("\n" + "="*60)
    print("TEST 2: Message Storage")
    print("="*60)
    
    mgr = get_firebase_manager()
    
    # Store some test messages
    test_messages = [
        ("Hello! I'm testing the chat system.", "user"),
        ("Hello! I'm Juno, your AI assistant. How can I help you today?", "assistant"),
        ("Tell me about yourself.", "user"),
        ("I'm an AI agent designed to help you with various tasks. I can answer questions, have conversations, and assist with many things!", "assistant"),
        ("That's great! Can you remember our conversation?", "user"),
        ("Yes! I have chat history enabled, so I can remember what we've discussed.", "assistant"),
    ]
    
    print(f"\n[2.1] Storing {len(test_messages)} test messages...")
    for content, role in test_messages:
        await mgr.store_message(
            user_id=user_id,
            content=content,
            role=role,
            agent_name="juno"
        )
        role_icon = "👤" if role == "user" else "🤖"
        print(f"  {role_icon} {role}: {content[:50]}...")
    
    print(f"\n  ✓ All messages stored successfully")


async def test_chat_history_loading(user_id: str):
    """Test loading chat history"""
    print("\n" + "="*60)
    print("TEST 3: Chat History Loading")
    print("="*60)
    
    mgr = get_firebase_manager()
    
    system_prompt = "You are Juno, a helpful AI assistant."
    
    print(f"\n[3.1] Loading chat history for user: {user_id}")
    chat_ctx = await mgr.load_chat_history(
        user_id=user_id,
        system_prompt=system_prompt,
        agent_name="juno",
        max_messages=50
    )
    
    # Display loaded messages
    print(f"\n[3.2] Loaded ChatContext contents:")
    print("-" * 40)
    
    # Access messages from ChatContext
    if hasattr(chat_ctx, 'messages'):
        messages = chat_ctx.messages
    elif hasattr(chat_ctx, 'items'):
        messages = chat_ctx.items
    else:
        messages = []
    
    for i, msg in enumerate(messages):
        role = msg.role if hasattr(msg, 'role') else "unknown"
        content = str(msg.content) if hasattr(msg, 'content') else str(msg)
        
        # Truncate long messages
        if len(content) > 100:
            content = content[:100] + "..."
        
        if role == "system":
            print(f"  📋 [{role}] {content}")
        elif role == "user":
            print(f"  👤 [{role}] {content}")
        else:
            print(f"  🤖 [{role}] {content}")
    
    print("-" * 40)
    print(f"  ✓ Total messages in context: {len(messages)}")


async def test_clear_history(user_id: str, confirm: bool = False):
    """Test clearing chat history"""
    print("\n" + "="*60)
    print("TEST 4: Clear History (Optional)")
    print("="*60)
    
    if not confirm:
        print("\n  ⚠️  Skipping clear history test (use --clear to enable)")
        return
    
    mgr = get_firebase_manager()
    
    print(f"\n[4.1] Clearing history for user: {user_id}")
    success = await mgr.clear_history(user_id, agent_name="juno")
    print(f"  ✓ History cleared: {success}")
    
    # Verify it's cleared
    print(f"\n[4.2] Verifying history is cleared...")
    chat_ctx = await mgr.load_chat_history(
        user_id=user_id,
        system_prompt="Test",
        agent_name="juno"
    )
    
    if hasattr(chat_ctx, 'messages'):
        messages = chat_ctx.messages
    elif hasattr(chat_ctx, 'items'):
        messages = chat_ctx.items
    else:
        messages = []
    
    # Should only have system messages, no user/assistant messages
    non_system = [m for m in messages if getattr(m, 'role', '') not in ['system']]
    print(f"  ✓ Remaining user/assistant messages: {len(non_system)}")


async def visualize_database_state(user_id: str):
    """Show current state of Firebase data"""
    print("\n" + "="*60)
    print("VISUALIZATION: Current Firebase State")
    print("="*60)
    
    mgr = get_firebase_manager()
    db = mgr.db
    
    # Show user document
    print(f"\n📁 Users Collection:")
    print("-" * 40)
    user_doc = db.collection('users').document(user_id).get()
    if user_doc.exists:
        data = user_doc.to_dict()
        print(f"  Document: users/{user_id}")
        for key, value in data.items():
            if isinstance(value, dict):
                print(f"    {key}: {{...}}")
            else:
                print(f"    {key}: {value}")
    else:
        print(f"  No user document found for {user_id}")
    
    # Show conversation document
    print(f"\n📁 Conversations Collection:")
    print("-" * 40)
    conv_id = f"{user_id}_juno"
    conv_doc = db.collection('conversations').document(conv_id).get()
    if conv_doc.exists:
        data = conv_doc.to_dict()
        messages = data.get('messages', [])
        print(f"  Document: conversations/{conv_id}")
        print(f"    user_id: {data.get('user_id')}")
        print(f"    agent_name: {data.get('agent_name')}")
        print(f"    created_at: {data.get('created_at')}")
        print(f"    updated_at: {data.get('updated_at')}")
        print(f"    messages: [{len(messages)} messages]")
        
        if messages:
            print(f"\n  Recent messages (last 5):")
            for msg in messages[-5:]:
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')[:60]
                print(f"    - {role}: {content}...")
    else:
        print(f"  No conversation document found for {conv_id}")


async def main():
    parser = argparse.ArgumentParser(description='Test Firebase User Manager')
    parser.add_argument('--user', type=str, default='test_user_benchmark',
                        help='User ID for testing (default: test_user_benchmark)')
    parser.add_argument('--clear', action='store_true',
                        help='Clear history after tests')
    parser.add_argument('--visualize-only', action='store_true',
                        help='Only visualize current state, no tests')
    
    args = parser.parse_args()
    user_id = args.user
    
    print("\n" + "🔥" * 30)
    print("  Firebase User Manager Test Suite")
    print("🔥" * 30)
    print(f"\nTest User ID: {user_id}")
    print(f"Working Directory: {os.getcwd()}")
    
    try:
        if args.visualize_only:
            await visualize_database_state(user_id)
        else:
            # Run all tests
            await test_user_session(user_id)
            await test_message_storage(user_id)
            await test_chat_history_loading(user_id)
            await test_clear_history(user_id, confirm=args.clear)
            await visualize_database_state(user_id)
        
        print("\n" + "="*60)
        print("✅ All tests completed successfully!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
