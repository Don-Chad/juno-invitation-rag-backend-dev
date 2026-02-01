import { NextRequest, NextResponse } from "next/server";
export const revalidate = 0;

export type ConnectionDetails = {
  serverUrl: string;
  roomName: string;
  participantName: string;
  participantToken: string;
};

export async function GET(request: NextRequest) {
  try {
    const authHeader = request.headers.get("Authorization");
    if (!authHeader || !authHeader.startsWith("Bearer ")) {
      return new NextResponse("Unauthorized: Missing or invalid token", { status: 401 });
    }

    // Proxy to the secure backend token server. This keeps LiveKit secrets off the frontend.
    const tokenServerUrl =
      process.env.TOKEN_SERVER_URL ??
      "http://127.0.0.1:3011/createToken";

    const resp = await fetch(tokenServerUrl, {
      method: "POST",
      headers: {
        Authorization: authHeader,
        "Content-Type": "application/json",
      },
      // body is optional; server enforces uid-based identity/room anyway
      body: JSON.stringify({}),
      cache: "no-store",
    });

    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      console.error("Token server error:", resp.status, text);
      
      // If it's a 403 (Subscription Required), pass it through so the frontend can handle it
      if (resp.status === 403) {
        return new NextResponse(text, { 
          status: 403,
          headers: { "Content-Type": "application/json" }
        });
      }
      
      return new NextResponse("Failed to get connection details", { status: resp.status });
    }

    const data = (await resp.json()) as ConnectionDetails;
    
    const headers = new Headers({
      "Cache-Control": "no-store",
    });
    return NextResponse.json(data, { headers });
  } catch (error) {
    if (error instanceof Error) {
      console.error(error);
      return new NextResponse(error.message, { status: 500 });
    }
    return new NextResponse("Internal Server Error", { status: 500 });
  }
}
