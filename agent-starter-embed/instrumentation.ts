// This file runs once when the Next.js server starts
export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    const maskSecret = (value: string | undefined) => {
      if (!value) return 'NOT SET';
      return value.length > 8 ? `${value.substring(0, 8)}...` : '***';
    };

    console.log('============================================================');
    console.log('FRONTEND ENVIRONMENT CONFIGURATION:');
    console.log('============================================================');
    console.log(`LIVEKIT_URL: ${process.env.LIVEKIT_URL || 'NOT SET'}`);
    console.log(`LIVEKIT_API_KEY: ${maskSecret(process.env.LIVEKIT_API_KEY)}`);
    console.log(`LIVEKIT_API_SECRET: ${maskSecret(process.env.LIVEKIT_API_SECRET)}`);
    console.log(`NEXT_PUBLIC_CONN_DETAILS_ENDPOINT: ${process.env.NEXT_PUBLIC_CONN_DETAILS_ENDPOINT || 'NOT SET'}`);
    console.log('============================================================');
  }
}

