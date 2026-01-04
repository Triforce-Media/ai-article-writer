# AI Article Writer

Automatically generate LinkedIn-style articles from YouTube video transcripts using Google Gemini AI.

## Features

- 📹 Download transcripts from up to 10 YouTube videos
- 🤖 Generate professional LinkedIn articles using Google Gemini AI
- 📝 Automatic title and hashtag generation
- 🔍 Optional Google Search integration for additional research
- 📊 Configurable article length (SHORT, MEDIUM, LONG)
- ⏱️ Rate limiting with delays between transcript downloads
- 🔄 Automatic commit and push to repository

## Setup

### 1. Add GitHub Secret

Add your Google Gemini API key as a GitHub secret:

1. Go to your repository settings
2. Navigate to **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `GEMINI_API_KEY`
5. Value: Your Google Gemini API key

### 2. Usage

#### Via GitHub Actions (Recommended)

1. Go to the **Actions** tab in your repository
2. Select **Generate Article from YouTube Transcripts**
3. Click **Run workflow**
4. Fill in the form:
   - **YouTube URL 1** (required): First YouTube video URL
   - **YouTube URL 2-10** (optional): Additional YouTube video URLs
   - **Context/Message** (optional): Description of what the article should be about
   - **Output size**: Choose SHORT (1-2 pages), MEDIUM (2-4 pages), or LONG (4-6 pages)
   - **Enable research**: Toggle Google Search integration for additional research
5. Click **Run workflow**

The workflow will:
- Download transcripts from all provided YouTube URLs (with 15-second delays between downloads)
- Generate an article using Google Gemini AI
- Save the article to the `articles/` directory
- Commit and push the article to the repository

#### Local Usage

You can also run the script locally:

```bash
# Install dependencies
pip install youtube-transcript-api google-genai

# Set your API key
export GEMINI_API_KEY="your-api-key-here"

# Run the script
python scripts/generate_article.py \
  --url-1 "https://www.youtube.com/watch?v=VIDEO_ID_1" \
  --url-2 "https://www.youtube.com/watch?v=VIDEO_ID_2" \
  --context "Technical deep-dive on distributed systems" \
  --output-size MEDIUM \
  --enable-research true
```

## Output

Generated articles are saved in the `articles/` directory with filenames based on the article title. Each article includes:

- A professional title
- LinkedIn-formatted content with proper spacing and formatting
- Relevant hashtags at the bottom

## Workflow Details

The GitHub Actions workflow:
- Runs on Ubuntu latest
- Uses Python 3.11
- Automatically installs required dependencies
- Downloads transcripts with 15-second delays to respect rate limits
- Generates articles using Google Gemini AI with high thinking level
- Commits and pushes results automatically

## Requirements

- Python 3.11+
- Google Gemini API key
- YouTube videos with available transcripts

## Notes

- The script tries to download English transcripts first, then falls back to any available language
- Transcripts are combined and analyzed together to create a unified narrative
- The AI filters out conversational noise and focuses on technical content
- Articles are formatted specifically for LinkedIn with proper spacing and engagement hooks
