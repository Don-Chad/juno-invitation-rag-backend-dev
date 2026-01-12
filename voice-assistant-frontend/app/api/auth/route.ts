import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";

// Store the password hash on the server side (environment variable)
// In production, this should be in .env.local as GRACE_PASSWORD_HASH
const PASSWORD_HASH = process.env.GRACE_PASSWORD_HASH || 
  // Default hash for "grace2025today" - CHANGE THIS IN PRODUCTION
  'df5d0a80104ff8eae2ea104149e5321113a2d194aa1c09029dc987b4114f882f';

// In-memory session store (in production, use Redis or a database)
const sessions = new Map<string, { 
  token: string; 
  createdAt: Date; 
  expiresAt: Date;
}>();

// Session expiry time (1 hour)
const SESSION_DURATION_MS = 60 * 60 * 1000;

// Clean up expired sessions periodically
setInterval(() => {
  const now = new Date();
  for (const [token, session] of sessions.entries()) {
    if (session.expiresAt < now) {
      sessions.delete(token);
    }
  }
}, 5 * 60 * 1000); // Clean every 5 minutes

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { password } = body;

    if (!password) {
      return NextResponse.json(
        { error: "Password is required" },
        { status: 400 }
      );
    }

    // Hash the provided password and compare with stored hash
    const providedHash = crypto.createHash('sha256').update(password).digest('hex');
    
    if (providedHash !== PASSWORD_HASH) {
      // Add delay to prevent brute force attacks
      await new Promise(resolve => setTimeout(resolve, 1000));
      return NextResponse.json(
        { error: "Invalid password" },
        { status: 401 }
      );
    }

    // Generate secure session token
    const token = crypto.randomBytes(32).toString('hex');
    const now = new Date();
    const expiresAt = new Date(now.getTime() + SESSION_DURATION_MS);

    // Store session
    sessions.set(token, {
      token,
      createdAt: now,
      expiresAt
    });

    // Return token with secure headers
    const response = NextResponse.json(
      { 
        success: true,
        token,
        expiresAt: expiresAt.toISOString()
      },
      { status: 200 }
    );

    // Set secure HTTP-only cookie (optional, for additional security)
    response.cookies.set('grace_session', token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'strict',
      maxAge: SESSION_DURATION_MS / 1000,
      path: '/'
    });

    return response;
  } catch (error) {
    console.error('Authentication error:', error);
    return NextResponse.json(
      { error: "Authentication failed" },
      { status: 500 }
    );
  }
}

export async function GET(request: NextRequest) {
  try {
    // Verify session endpoint
    const authHeader = request.headers.get('Authorization');
    const cookieToken = request.cookies.get('grace_session')?.value;
    
    const token = authHeader?.replace('Bearer ', '') || cookieToken;

    if (!token) {
      return NextResponse.json(
        { error: "No session token provided" },
        { status: 401 }
      );
    }

    const session = sessions.get(token);
    
    if (!session) {
      return NextResponse.json(
        { error: "Invalid session" },
        { status: 401 }
      );
    }

    if (session.expiresAt < new Date()) {
      sessions.delete(token);
      return NextResponse.json(
        { error: "Session expired" },
        { status: 401 }
      );
    }

    return NextResponse.json(
      { 
        valid: true,
        expiresAt: session.expiresAt.toISOString()
      },
      { status: 200 }
    );
  } catch (error) {
    console.error('Session verification error:', error);
    return NextResponse.json(
      { error: "Session verification failed" },
      { status: 500 }
    );
  }
}

export async function DELETE(request: NextRequest) {
  try {
    // Logout endpoint
    const authHeader = request.headers.get('Authorization');
    const cookieToken = request.cookies.get('grace_session')?.value;
    
    const token = authHeader?.replace('Bearer ', '') || cookieToken;

    if (token) {
      sessions.delete(token);
    }

    const response = NextResponse.json(
      { success: true },
      { status: 200 }
    );

    // Clear the cookie
    response.cookies.delete('grace_session');

    return response;
  } catch (error) {
    console.error('Logout error:', error);
    return NextResponse.json(
      { error: "Logout failed" },
      { status: 500 }
    );
  }
}
