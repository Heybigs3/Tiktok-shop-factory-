# TikTok App Submission — Complete Checklist

## App: dailyfindsNYC
## Client Key: awlyc89ck0xtve48

---

## BLOCKERS — Things That Will Get You Instantly Rejected

### 1. You Need a Real Website
TikTok requires:
> "A valid official website that houses information about your web and services. Your website URL cannot be a landing page or login page. You must have an externally facing fully developed website."

**And on that website:**
> "Your Privacy Policy and Terms of Service links must be visible on the website URL without having to open a menu to view them, and the links must be active."

This means you need a real website (e.g., `dailyfindsnyc.com`) with:
- A homepage explaining what your app/service does
- A visible Privacy Policy link (not hidden in a menu)
- A visible Terms of Service link (not hidden in a menu)
- Both links must work and lead to full pages

**A Notion page or GitHub Pages won't cut it** — it needs to look like a real product website. Options:
- **Carrd.co** ($19/year) — simple one-page site with custom domain
- **Wix / Squarespace** — free tier works, custom domain is better
- **GitHub Pages with custom domain** — free, more work to set up
- **Buy a domain** (Namecheap, ~$10/year) and point it to whichever hosting you pick

### 2. Demo Video Must Use Sandbox
> "If your app has not been approved before, you are required to use a sandbox environment."

You need to:
1. Toggle to **Sandbox** mode in the developer portal
2. Get sandbox API credentials
3. Configure the dashboard to use sandbox endpoints
4. Record the demo against the sandbox environment

### 3. App Must Not Be "In Development"
> "Apps that are still in development or testing will not be approved."

The dashboard publish page needs to be **fully built and functional** before you submit. Not a prototype, not a mockup — a working product.

### 4. Redirect URI Required for Web Apps
> "You must provide a valid redirect URI under the web app configuration section."

You need to set your OAuth redirect URI in the developer portal. Currently it's `http://localhost:8585/callback` — TikTok may require a real domain for production. Check if sandbox allows localhost.

---

## Step 1: Basic Information

### App Icon
- 1024x1024 pixels, JPEG/JPG/PNG, under 5MB
- Must be a clear, professional image
- Must not be confused with another well-known brand
- Must be consistent with the app name "dailyfindsNYC"
- Design one in Canva (free) — use your brand colors/style

### App Name
- Already set: **dailyfindsNYC** — this is fine
- Does not reference social media companies
- Matches your brand name (not a description of the app)
- Will be shown on the TikTok authorization page

### Category
- Select the most appropriate category from the dropdown

### Description (max 120 characters)
Suggested:

> Create and publish short-form videos to TikTok. Review, edit, and post content with full creative control.

97 characters. Emphasizes human control.

### Website URL
A fully developed website for dailyfindsNYC. Must have:
- Homepage with information about your service
- Privacy Policy link visible WITHOUT opening a menu
- Terms of Service link visible WITHOUT opening a menu
- Both links must be active and lead to full pages

### Terms of Service
Must be hosted on your website (not a separate domain). Should cover:
- What your app does
- User responsibilities
- Content ownership (users own their content)
- Limitation of liability
- AI-generated content disclosure
- Account termination conditions

### Privacy Policy
Must be hosted on your website. Should cover:
- What data you collect (OAuth tokens, TikTok username)
- How data is stored (locally on user's machine, not on servers)
- No data is shared with third parties
- No analytics or tracking
- How to delete data (revoke access, delete token file)
- Contact information for privacy inquiries
- COPPA/GDPR compliance statement

### Platform
- Select **Web**
- Configure the **redirect URI** in the web app section

---

## Step 2: Add Products

Click "Add products" and add exactly:

1. **Login Kit** — OAuth authentication
2. **Content Posting API** — video publishing

Do NOT add anything else. TikTok says unused products delay review.

---

## Step 3: Add Scopes

Click "Add scopes" and add exactly:

| Scope | Required By | Purpose |
|-------|-------------|---------|
| `user.info.basic` | Login Kit | Display creator name during publish |
| `video.upload` | Content Posting API | Upload video files |
| `video.publish` | Content Posting API | Post to creator's profile |

Do NOT add scopes you don't use.

---

## Step 4: Explanation (max 1000 characters)

Paste this into the explanation field:

```
Login Kit: Users connect their TikTok account via OAuth 2.0. The app opens TikTok's authorization page in the browser. After login, we store the access token locally. We use user.info.basic to display the creator's nickname and avatar in our web dashboard so they can confirm which account they are posting to.

Content Posting API: Users create short-form videos in our web dashboard, then publish to TikTok. Before posting, we call creator_info to get privacy options and interaction settings. The user selects privacy level (no default), toggles interactions (all off by default), enters a title, and optionally enables commercial content disclosure. We display an AI-generated content notice and TikTok's Music Usage Confirmation. The user must explicitly confirm before posting. We use video.upload to transfer the file and video.publish to post it. All posts set is_aigc:true. Posts are capped at 15/day per creator.
```

That's 893 characters.

---

## Step 5: Demo Video

### CRITICAL: Record Using Sandbox
1. Toggle to "Sandbox" at the top of the developer portal
2. Use sandbox credentials in your `.env`
3. Record the entire flow in the **web dashboard** (browser)

### What to Show (In This Order)
The video must demonstrate ALL products and scopes:

**Login Kit + user.info.basic:**
1. Open the dashboard in browser — show the URL in the address bar
2. Click "Connect TikTok Account"
3. TikTok OAuth page opens — log in and authorize
4. Dashboard shows "Logged in as [name] (@username)" — proves user.info.basic works

**Content Posting API + video.upload + video.publish:**
5. Browse the video queue — select a video
6. Watch/preview the video in the player
7. Select privacy level from dropdown — show NO default is selected
8. Show interaction toggles — ALL off by default
9. Type a title with hashtags
10. Show commercial content toggle (off by default) — turn it ON and select a disclosure type
11. Show AI-generated content notice on screen
12. Show Music Usage Confirmation on screen
13. Check the consent checkbox
14. Click publish
15. Show success confirmation with publish ID

**Key rules:**
- The domain shown in the browser MUST match your registered website URL
- All selected products and scopes must be clearly demonstrated
- Show the full UI and all user interactions
- Go slowly so reviewers can read every element

### Video Format
- MP4 or MOV, under 50MB per file
- Up to 5 files total
- Record at 1080p, clean browser, no other tabs

---

## Step 6: Pre-Submission Checklist

### Basic Info
- [ ] App icon uploaded (1024x1024, professional, matches brand)
- [ ] App name is set and doesn't reference TikTok
- [ ] Category selected
- [ ] Description filled in (under 120 chars)
- [ ] Website URL provided (fully developed site, not a landing page)
- [ ] Privacy Policy link visible on website homepage (no menu click required)
- [ ] Terms of Service link visible on website homepage (no menu click required)
- [ ] Both links are active and lead to full pages
- [ ] Platform set to "Web"
- [ ] Redirect URI configured in web app section

### Products & Scopes
- [ ] Login Kit added
- [ ] Content Posting API added
- [ ] No unused products added
- [ ] user.info.basic scope added
- [ ] video.upload scope added
- [ ] video.publish scope added
- [ ] No unused scopes added

### App Review
- [ ] Explanation written (under 1000 chars, covers all products and scopes)
- [ ] Demo video recorded using Sandbox environment
- [ ] Demo video shows Login Kit flow (OAuth + user info display)
- [ ] Demo video shows Content Posting API flow (full publish with all settings)
- [ ] Demo video shows the actual web dashboard (not a mockup)
- [ ] Browser URL in video matches registered website URL
- [ ] Video is clear, readable, shows all UI interactions
- [ ] Video uploaded to the portal (MP4/MOV, under 50MB)

### App Readiness
- [ ] Dashboard publish page is fully built and functional
- [ ] App is not "in development" — it's a finished, working product
- [ ] Sandbox integration tested and working

Click **"Submit for review"** only when EVERY box is checked.

---

## After Submission

- Review typically takes **1-2 weeks**
- Check the **"Review comments"** tab for feedback
- If rejected: fix issues, update explanation/video, resubmit
- After approval: switch to Production mode, update API endpoints

---

## Priority Order — What to Do First

1. **Build the website** — get a domain, create a site with ToS and Privacy Policy visible on homepage
2. **Finish the dashboard publish page** — the other Claude is on this
3. **Create the app icon** — Canva, 5 minutes
4. **Set up sandbox** — toggle to sandbox in portal, get sandbox credentials
5. **Test the full flow** in sandbox with the web dashboard
6. **Record the demo video** — only after everything above works
7. **Fill in all portal fields** — description, category, URLs, redirect URI, products, scopes, explanation
8. **Submit**
