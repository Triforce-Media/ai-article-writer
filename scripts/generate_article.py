#!/usr/bin/env python3
"""
Generate LinkedIn article from YouTube transcripts using Google Gemini API.
"""

import sys
import re
import os
import time
import argparse
from pathlib import Path
from datetime import datetime

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    print("Installing youtube-transcript-api...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "youtube-transcript-api", "-q"])
    from youtube_transcript_api import YouTubeTranscriptApi

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Installing google-genai...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "google-genai", "-q"])
    from google import genai
    from google.genai import types


def get_video_id(url):
    """Extract video ID from YouTube URL."""
    if not url or url.strip() == "":
        return None
    
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    if len(url.strip()) == 11:
        return url.strip()
    raise ValueError(f"Could not extract video ID from: {url}")


def download_transcript(video_id, delay=15):
    """Download transcript for a video ID with optional delay."""
    print(f"Getting transcript for video: {video_id}...")
    
    ytt_api = YouTubeTranscriptApi()
    
    # Try English first, then any available language
    try:
        fetched_transcript = ytt_api.fetch(video_id, languages=['en', 'en-US', 'en-GB'])
    except:
        # If English doesn't work, try any available language
        fetched_transcript = ytt_api.fetch(video_id)
    
    # Combine transcript snippets into text
    transcript_text = ' '.join([snippet.text for snippet in fetched_transcript])
    
    print(f"✓ Downloaded transcript ({len(fetched_transcript)} entries, {len(transcript_text)} chars)")
    
    # Wait before next download
    if delay > 0:
        print(f"Waiting {delay} seconds before next download...")
        time.sleep(delay)
    
    return transcript_text


def build_prompt(transcripts, context_message, output_size, enable_research):
    """Build the prompt for the Gemini API."""
    
    # Build transcript content
    transcript_content = ""
    for i, transcript in enumerate(transcripts, 1):
        transcript_content += f"\n\n--- TRANSCRIPT {i} ---\n\n{transcript}\n"
    
    # Build context block
    context_block = ""
    if context_message and context_message.strip():
        context_block = f"""
CONTEXT BLOCK:
Topic: {context_message}
Angle: Technical deep-dive with practical insights
Audience: Senior engineers and technical practitioners
"""
    
    # Adjust system instruction based on output size
    size_guidance = {
        "SHORT": "The article should be approximately 1-2 pages long (500-1000 words).",
        "MEDIUM": "The article should be approximately 2-4 pages long (1000-2000 words).",
        "LONG": "The article should be approximately 4-6 pages long (2000-3000 words)."
    }
    
    system_instruction = f"""ROLE & OBJECTIVE:
You are a Senior Technical Evangelist and Engineering Editor. Your goal is to ingest multiple raw transcripts (attached by the user), filter out conversational noise, synthesize the technical concepts, and produce a high-impact, "viral-style" LinkedIn article. It should be informative, and provide core concepts to people. {size_guidance.get(output_size, size_guidance['MEDIUM'])}

YOUR DATA SOURCE:
The user will attach multiple files (transcripts/notes). These contain the source of truth.
Prioritize Synthesis: Do not just summarize one file after another. Look for patterns, conflicting opinions, and complementary technical details across all provided files to create a unified narrative.
Ignore Fluff: Disregard conversational filler (e.g., "Can you hear me?", "Next slide", jokes). Focus purely on architectural details, technical trade-offs, and engineering insights.

CONTENT GUIDELINES:
Fairness is Key: When comparing technologies (e.g., Ray vs. Triton), you must be objective. Highlight where Tool A shines and where Tool B is better. Avoid marketing hype; focus on engineering reality.
Depth: The content must be useful to a technical practitioner. Do not stay on the surface.

OUTPUT FORMATTING (STRICT LINKEDIN STYLE):
The Hook: Start with a punchy, 1-2 sentence hook. No "In this post" or "Today we discuss." Jump straight into the tension or the value proposition.
Structure:
Use short paragraphs (1-2 sentences max).
Use double line breaks for "white space" readability.
Use bullet points for technical comparisons or feature lists.
Tone: Professional, insightful, slightly conversational but highly technical.
Emojis: Use them to break up text, but do not overdo it. (e.g., 🚀 🛠️ 💡).
Engagement: End with a specific question to the audience to drive comments.
Hashtags: 3-5 relevant tags at the very bottom.

IMPORTANT OUTPUT REQUIREMENTS:
1. The article title should be on the first line, prefixed with "TITLE: "
2. The article content should follow after a blank line
3. At the end, include a line with "HASHTAGS: " followed by 3-5 relevant hashtags separated by spaces

INTERACTION MODEL:
The user will provide the files and a specific "Context Block" containing the Topic, Angle, and Audience. You will wait for this input, analyze the attached files based on those variables, and generate the post."""
    
    user_prompt = f"""{context_block}

Please analyze the following transcripts and generate a LinkedIn article based on the guidelines above:

{transcript_content}

Remember to:
1. Start your response with "TITLE: " followed by the article title
2. Include the full article content
3. End with "HASHTAGS: " followed by 3-5 relevant hashtags"""
    
    return system_instruction, user_prompt


def generate_article(transcripts, context_message, output_size, enable_research):
    """Generate article using Gemini API."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")
    
    client = genai.Client(api_key=api_key)
    
    system_instruction, user_prompt = build_prompt(transcripts, context_message, output_size, enable_research)
    
    # Using gemini-3-pro-preview as per user's example
    # If this model is not available, try: "gemini-1.5-pro" or "gemini-2.0-flash-exp"
    model = "gemini-3-pro-preview"
    
    # Build tools based on enable_research flag
    tools = []
    if enable_research:
        tools = [
            types.Tool(url_context=types.UrlContext()),
            types.Tool(googleSearch=types.GoogleSearch()),
        ]
    
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=user_prompt),
            ],
        ),
    ]
    
    generate_content_config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_level="HIGH",
        ),
        tools=tools if tools else None,
        system_instruction=[
            types.Part.from_text(text=system_instruction),
        ],
    )
    
    print("\n🤖 Generating article with Gemini API...")
    print("This may take a few minutes...\n")
    
    full_response = ""
    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    ):
        if chunk.text:
            full_response += chunk.text
            print(chunk.text, end="", flush=True)
    
    print("\n\n✓ Article generation complete!\n")
    
    return full_response


def parse_article_response(response):
    """Parse the response to extract title, content, and hashtags."""
    title = None
    content = response
    hashtags = []
    
    # Extract title
    title_match = re.search(r'^TITLE:\s*(.+?)$', response, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
        # Remove title line from content
        content = re.sub(r'^TITLE:\s*.+?$', '', content, flags=re.MULTILINE).strip()
    
    # Extract hashtags
    hashtags_match = re.search(r'HASHTAGS:\s*(.+?)$', response, re.MULTILINE | re.DOTALL)
    if hashtags_match:
        hashtags_text = hashtags_match.group(1).strip()
        hashtags = [tag.strip() for tag in hashtags_text.split() if tag.strip()]
        # Remove hashtags line from content
        content = re.sub(r'HASHTAGS:\s*.+?$', '', content, flags=re.MULTILINE | re.DOTALL).strip()
    
    # If no title found, generate a default one
    if not title:
        title = f"Article_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    return title, content, hashtags


def sanitize_filename(title):
    """Convert title to a valid filename."""
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '', title)
    # Replace spaces with underscores
    filename = re.sub(r'\s+', '_', filename)
    # Limit length
    if len(filename) > 100:
        filename = filename[:100]
    return filename


def main():
    parser = argparse.ArgumentParser(description='Generate LinkedIn article from YouTube transcripts')
    parser.add_argument('--url-1', required=True, help='YouTube URL 1')
    parser.add_argument('--url-2', default='', help='YouTube URL 2 (optional)')
    parser.add_argument('--url-3', default='', help='YouTube URL 3 (optional)')
    parser.add_argument('--url-4', default='', help='YouTube URL 4 (optional)')
    parser.add_argument('--url-5', default='', help='YouTube URL 5 (optional)')
    parser.add_argument('--url-6', default='', help='YouTube URL 6 (optional)')
    parser.add_argument('--url-7', default='', help='YouTube URL 7 (optional)')
    parser.add_argument('--url-8', default='', help='YouTube URL 8 (optional)')
    parser.add_argument('--url-9', default='', help='YouTube URL 9 (optional)')
    parser.add_argument('--url-10', default='', help='YouTube URL 10 (optional)')
    parser.add_argument('--context', default='', help='Context message about the article (optional)')
    parser.add_argument('--output-size', default='MEDIUM', choices=['SHORT', 'MEDIUM', 'LONG'], 
                       help='Output size (default: MEDIUM)')
    parser.add_argument('--enable-research', type=lambda x: x.lower() == 'true', default=True,
                       help='Enable additional research (default: true)')
    parser.add_argument('--delay', type=int, default=15, help='Delay between transcript downloads in seconds (default: 15)')
    
    args = parser.parse_args()
    
    # Collect all non-empty URLs
    urls = [
        args.url_1, args.url_2, args.url_3, args.url_4, args.url_5,
        args.url_6, args.url_7, args.url_8, args.url_9, args.url_10
    ]
    urls = [url for url in urls if url and url.strip()]
    
    if not urls:
        print("Error: At least one YouTube URL is required", file=sys.stderr)
        sys.exit(1)
    
    print(f"📹 Processing {len(urls)} YouTube video(s)...\n")
    
    # Download transcripts
    transcripts = []
    video_ids = []
    for i, url in enumerate(urls, 1):
        try:
            video_id = get_video_id(url)
            video_ids.append(video_id)
            transcript = download_transcript(video_id, delay=args.delay if i < len(urls) else 0)
            transcripts.append(transcript)
        except Exception as e:
            print(f"⚠️  Error downloading transcript for {url}: {e}", file=sys.stderr)
            print(f"   Skipping this video and continuing...\n")
    
    if not transcripts:
        print("Error: No transcripts were successfully downloaded", file=sys.stderr)
        sys.exit(1)
    
    print(f"\n✓ Successfully downloaded {len(transcripts)} transcript(s)\n")
    
    # Generate article
    try:
        response = generate_article(
            transcripts,
            args.context,
            args.output_size,
            args.enable_research
        )
    except Exception as e:
        print(f"Error generating article: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Parse response
    title, content, hashtags = parse_article_response(response)
    
    # Create articles directory
    articles_dir = Path("articles")
    articles_dir.mkdir(exist_ok=True)
    
    # Save article
    filename = sanitize_filename(title)
    filepath = articles_dir / f"{filename}.md"
    
    # Format the article with title and hashtags
    article_content = f"# {title}\n\n"
    article_content += content
    if hashtags:
        article_content += f"\n\n---\n\n**Hashtags:** {' '.join(hashtags)}\n"
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(article_content)
    
    print(f"\n✓ Article saved to: {filepath}")
    print(f"  Title: {title}")
    print(f"  Hashtags: {', '.join(hashtags) if hashtags else 'None'}")


if __name__ == '__main__':
    main()
