# 📊 Historical Data Backfill Guide

## Problem
Your yearly sentiment chart only shows recent data (last few weeks) because the database only contains posts collected since you started the project.

## Solution
Run the **one-time historical backfill script** to populate your database with posts from the past year.

---

## How to Use

### Step 1: Stop Your API (if running)
```bash
# Press Ctrl+C in the terminal where main.py is running
```

### Step 2: Run the Backfill Script
```bash
cd sentiment-analysis-backend
python backfill_historical_data.py
```

### Step 3: Follow the Prompts
```
Start backfill? This may take 5-10 minutes. (yes/no): yes
```

### Step 4: Wait for Completion
The script will:
- ✅ Collect top posts from the past month
- ✅ Collect top posts from the past year
- ✅ Collect top political posts of all time
- ✅ Filter for political content (2+ keywords)
- ✅ Analyze sentiment
- ✅ Save to database (skips duplicates automatically)

Expected output:
```
🔄 STARTING HISTORICAL DATA BACKFILL
================================

📅 Top posts from the past month
------------------------------------------------------------
  📍 Collecting from r/argentina (month)...
    ✓ Found 10 political posts...
    ✓ Found 20 political posts...
  ✅ Collected 25 posts from r/argentina
  ...

💾 Saving 150 posts to database...

📊 BACKFILL COMPLETE!
================================
✅ Total posts collected: 150
📅 Date range: 2024-01-15 to 2025-11-04
⏱️  Time span: 294 days

📈 Sentiment breakdown:
  😊 Positive: 45 (30.0%)
  😠 Negative: 68 (45.3%)
  😐 Neutral: 37 (24.7%)

✨ Your yearly sentiment trend chart should now have data!
   Refresh the dashboard to see historical trends.
```

### Step 5: Restart Your API
```bash
python main.py
```

### Step 6: Refresh Your Dashboard
1. Go to your sentiment analysis dashboard
2. Click the **Refresh** button
3. Click **Yearly** time range
4. You should now see data spanning months or a full year! 🎉

---

## What Gets Collected

### Subreddits
- r/argentina
- r/RepublicaArgentina  
- r/ArgentinaPolitica

### Time Periods
1. **Month:** Top 100 posts from the past 30 days
2. **Year:** Top 150 posts from the past 365 days
3. **All Time:** Top 100 political posts ever

### Total Expected
- Approximately 100-300 political posts
- Spanning several months to a full year
- Automatically skips duplicates

---

## Important Notes

### ✅ Safe to Run Multiple Times
- The script checks for existing posts and skips duplicates
- You can run it again if you want more historical data
- No data will be lost or overwritten

### ⏱️ Takes Time
- Expect 5-10 minutes for full completion
- Reddit API has rate limits (script includes delays)
- Progress is shown in real-time

### 🔄 Run Once, Not Regularly
- This is a **one-time** backfill script
- Your regular API (`main.py`) will collect new posts automatically
- Only run again if you want to expand historical coverage

### 🔍 Political Filter
- Only collects posts with 2+ political keywords
- Some subreddits may have fewer political posts than expected
- This ensures high-quality, relevant data

---

## Troubleshooting

### "No posts were collected"
**Possible causes:**
- Political filter too strict
- Reddit API rate limits hit
- Subreddits don't have many political posts

**Solutions:**
- Wait 30 minutes and try again (rate limits)
- Check your Reddit API credentials in `.env`
- Consider lowering the political keyword requirement (edit `reddit_collector.py`)

### "Error: Reddit API"
**Check:**
- `.env` file has valid Reddit API credentials
- Internet connection is working
- Reddit isn't experiencing downtime

### "Database locked"
**Solution:**
- Make sure `main.py` is NOT running
- Close any other database connections
- Try again

### Still Not Showing Yearly Data?
**Check console logs:**
```typescript
📈 Trend data points: 150  ← Should be > 100 for good yearly view
📅 Date range: 2024-01 to 2025-11  ← Should span ~1 year
```

**If data range is still short:**
1. Run backfill script again
2. Try collecting from more subreddits (edit script)
3. Check if historical posts exist in those subreddits

---

## After Backfill

### Your Dashboard Will Show:
✅ Yearly chart with 6-12 months of data  
✅ Smooth sentiment trends over time  
✅ More reliable percentage calculations  
✅ Better visualization of long-term patterns  

### Going Forward:
- Regular API collects new posts every 2 hours
- Database grows organically
- No need to run backfill again
- Historical data is preserved

---

## Advanced: Customize the Backfill

Edit `backfill_historical_data.py` to adjust:

### Collect More Posts
```python
time_periods = [
    ('month', 200, 'Top posts from the past month'),  # Increased from 100
    ('year', 300, 'Top posts from the past year'),    # Increased from 150
    ('all', 200, 'Top posts of all time')             # Increased from 100
]
```

### Add More Subreddits
```python
for subreddit in ['argentina', 'RepublicaArgentina', 'ArgentinaPolitica', 'republica_argentina']:
    # Add more subreddits here
```

### Change Political Filter
Edit `reddit_collector.py`:
```python
def is_political(self, text: str) -> bool:
    matches = sum(1 for keyword in self.political_keywords if keyword in text_lower)
    return matches >= 1  # Lower from 2 to 1 for more posts
```

---

## Questions?

**Q: How often should I run this?**  
A: Once is enough! Your regular API handles new posts.

**Q: Will this slow down my API?**  
A: No, run it while the API is stopped, then restart.

**Q: Can I delete old posts?**  
A: Yes, but you'll lose historical trend data. Not recommended.

**Q: What if I want data from 2+ years ago?**  
A: Reddit's API limits how far back you can fetch. "All time" gets the oldest available top posts.

---

**Ready to get a full year of sentiment data? Run the backfill script! 🚀**



