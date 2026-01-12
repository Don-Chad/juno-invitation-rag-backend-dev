# Supabase Authentication Setup

## Current Issue
Signups are disabled on your Supabase instance, preventing user creation through the app.

## Quick Fix: Enable Signups

1. **Go to Supabase Dashboard**
   - URL: https://supabase.com/dashboard/project/kanuhstcviwvixbjojvq

2. **Enable Email Signups**
   - Navigate to: **Authentication** → **Providers** → **Email**
   - Toggle ON: **"Enable email signup"**
   - Toggle ON: **"Confirm email"** (optional - if OFF, users can login immediately)
   - Save changes

3. **Create Users Manually (Alternative)**
   - Navigate to: **Authentication** → **Users**
   - Click: **"Add user"**
   - Email: `focabaas@gmail.com`, Password: `945hasfkl034ok%`
   - Click: **"Add user"**
   - Repeat for: `mark@dopamine.amterdam`, Password: `jsdfkksfd405al`

## For Admin Panel (Future Enhancement)

To enable server-side user creation (admin can create users without public signups):

1. **Get Service Role Key**
   - Go to: **Settings** → **API**
   - Copy: **"service_role key"** (secret - keep it safe!)

2. **Add to Backend .env**
   ```bash
   # Add to /home/mark/projects/12_custom_dorpsbot_configuration_frontend/pulse-robot-template-57736-32260/.env
   SUPABASE_SERVICE_ROLE_KEY="your_service_role_key_here"
   ```

3. **Then we can build admin panel** that creates users via backend API

## Current Configuration

- **Project ID**: kanuhstcviwvixbjojvq
- **URL**: https://kanuhstcviwvixbjojvq.supabase.co
- **Anon Key**: (already configured - public key)
- **Service Role**: Not configured yet

## Recommended: Manual User Creation Now

For immediate access:
1. Go to Supabase dashboard
2. Authentication → Users → Add user
3. Create both users manually
4. Users can then login at `http://localhost:3004/auth`

Then later we can add proper admin panel.
