# Screen Recording Guide — TikTok App Review

TikTok requires a screen recording demonstrating the full publishing UX flow. This guide tells you exactly what to show.

## Before Recording

1. Make sure you have at least one rendered video in `output/videos/`
2. Make sure your TikTok OAuth token is cleared (delete `data/tokens/tiktok_token.json`) so the recording shows the full login flow
3. Use a screen recorder (Windows: Win+G → Record, or OBS Studio)
4. Record your terminal at a readable font size

## What to Record (Step by Step)

### Scene 1: Launch the Publisher
```bash
python -m src.publishers.tiktok_publisher
```
Show the welcome banner and Step 1 starting.

### Scene 2: OAuth Login
- Browser opens to TikTok login page
- Log in with your TikTok account
- Click "Authorize"
- Show the "Logged in!" browser page
- Show the terminal confirming: "Login successful! Token saved."

### Scene 3: Creator Info
- Show the app displaying "Posting as: [your name] (@username)"
- Show the daily post count ("Posts today: 0/15")

### Scene 4: Video Selection
- Show the list of available videos
- Pick one by typing its number
- Show the video preview panel (filename, size, script content)

### Scene 5: Privacy Level
- Show the privacy options listed (from the API — NOT hardcoded)
- Show that NO option is pre-selected
- Select one by typing its number

### Scene 6: Interaction Settings
- Show all three toggles (Comments, Duets, Stitches)
- Show they are all OFF by default (user must opt-in)
- If any are disabled in TikTok settings, show them greyed out
- Toggle one on (e.g., allow comments) to demonstrate it works

### Scene 7: Title/Caption
- Type a title with hashtags
- Show it accepts the input

### Scene 8: Commercial Content
- Show the commercial content question (default: No)
- Answer "y" to show the disclosure flow
- Show that you MUST select at least one option
- Show what happens if you try to select neither (validation error)
- Select one to proceed

### Scene 9: Final Confirmation
- Show the full confirmation panel with:
  - Video filename
  - Title
  - Privacy level
  - AI-generated content notice
  - Music Usage Confirmation text
- Show that user must type "yes" (not just press Enter)
- Type "yes" to confirm

### Scene 10: Upload
- Show the upload progress
- Show the success message with Publish ID
- Show the status check command

### Scene 11 (Optional): Status Check
```bash
python -m src.publishers.tiktok_publisher --status [publish_id]
```
- Show the post status response

## Recording Tips

- Keep the recording under 5 minutes
- Use a clean terminal (no other windows visible)
- Pause briefly at each step so reviewers can read the screen
- If something fails, just re-record — don't include error recovery unless you want to show error handling
- Export as MP4 at 1080p resolution

## File Naming
Name the recording: `tiktok_factory_ux_demo.mp4`
