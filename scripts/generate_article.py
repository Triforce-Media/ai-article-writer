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
import urllib.request
import urllib.parse
from urllib.error import URLError, HTTPError

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


def get_formatting_guidelines(article_type):
    """Get formatting guidelines based on article type."""
    guidelines = {
        "LinkedIn Article": """OUTPUT FORMATTING (STRICT LINKEDIN STYLE):
The Hook: Start with a punchy, 1-2 sentence hook. No "In this post" or "Today we discuss." Jump straight into the tension or the value proposition.
Structure:
Use short paragraphs (1-2 sentences max).
Use double line breaks for "white space" readability.
Use bullet points for technical comparisons or feature lists.
Tone: Professional, insightful, slightly conversational but highly technical.
Emojis: Use them to break up text, but do not overdo it. (e.g., 🚀 🛠️ 💡).
Engagement: End with a specific question to the audience to drive comments.
Hashtags: 3-5 relevant tags at the very bottom.""",
        "LinkedIn Post": """OUTPUT FORMATTING (LINKEDIN POST STYLE):
Keep it concise and punchy (under 3000 characters).
Start with a strong hook that grabs attention.
Use short paragraphs and line breaks for readability.
Include emojis sparingly for visual appeal.
End with a call-to-action or question.
Hashtags: 3-5 relevant tags at the bottom.""",
        "Substack": """OUTPUT FORMATTING (SUBSTACK STYLE):
Professional newsletter/article format.
Longer form content with clear sections.
Use headers and subheaders to break up content.
Include engaging introduction and conclusion.
More narrative and storytelling approach.
No hashtags needed.""",
        "Reddit Post": """OUTPUT FORMATTING (REDDIT POST STYLE):
Conversational and engaging tone.
Use clear formatting with headers and bullet points.
Include TL;DR (Too Long; Didn't Read) summary at the top.
Engage with the community style - ask questions, invite discussion.
Use markdown formatting for readability.
No hashtags needed.""",
        "Blog Post": """OUTPUT FORMATTING (BLOG POST STYLE):
Professional blog article format.
Clear introduction, body, and conclusion.
Use headers and subheaders for structure.
Include engaging narrative and examples.
SEO-friendly structure.
No hashtags needed.""",
        "Twitter Thread": """OUTPUT FORMATTING (TWITTER THREAD STYLE):
Break content into tweet-sized chunks (280 characters each).
Number each tweet (1/n, 2/n, etc.).
Start with a hook tweet that grabs attention.
Each tweet should be self-contained but part of a narrative.
Use emojis and formatting for engagement.
Include a final tweet with key takeaways.
No hashtags needed."""
    }
    return guidelines.get(article_type, guidelines["LinkedIn Article"])


def extract_links(text):
    """Extract URLs from text."""
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+[^\s<>"{}|\\^`\[\].,;:!?]'
    urls = re.findall(url_pattern, text)
    return urls


def verify_link(url):
    """Verify that a link is accessible."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status == 200
    except (URLError, HTTPError, ValueError, Exception):
        return False


def build_prompt(transcripts, context_message, additional_info, article_type, word_count, audience, enable_research):
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
Audience: {audience}
"""
    else:
        context_block = f"""
CONTEXT BLOCK:
Angle: Technical deep-dive with practical insights
Audience: {audience}
"""
    
    # Add additional info block if provided
    additional_block = ""
    if additional_info and additional_info.strip():
        # Extract links from additional_info
        links = extract_links(additional_info)
        links_text = ""
        if links:
            links_text = "\n\nIMPORTANT: The following links are provided for you to review and potentially reference:\n" + "\n".join(f"- {link}" for link in links)
        
        additional_block = f"""
ADDITIONAL INFORMATION:
{additional_info}{links_text}

Please review any provided links and incorporate relevant information from them into the article.
"""
    
    # Word count guidance
    word_count_int = int(word_count)
    size_guidance = f"The {article_type.lower()} should be approximately {word_count_int} words (target: {word_count_int} words, acceptable range: {int(word_count_int * 0.9)}-{int(word_count_int * 1.1)} words)."
    
    formatting_guidelines = get_formatting_guidelines(article_type)
    
    system_instruction = f"""ROLE & OBJECTIVE:
You are a Senior Technical Evangelist and Engineering Editor. Your goal is to ingest multiple raw transcripts (attached by the user), filter out conversational noise, synthesize the technical concepts, and produce a high-impact {article_type.lower()}. It should be informative, and provide core concepts to people. {size_guidance}

YOUR DATA SOURCE:
The user will attach multiple files (transcripts/notes). These contain the source of truth.
Prioritize Synthesis: Do not just summarize one file after another. Look for patterns, conflicting opinions, and complementary technical details across all provided files to create a unified narrative.
Ignore Fluff: Disregard conversational filler (e.g., "Can you hear me?", "Next slide", jokes). Focus purely on architectural details, technical trade-offs, and engineering insights.

CONTENT GUIDELINES:
Fairness is Key: When comparing technologies (e.g., Ray vs. Triton), you must be objective. Highlight where Tool A shines and where Tool B is better. Avoid marketing hype; focus on engineering reality.
Depth: The content must be useful to a technical practitioner. Do not stay on the surface.

{formatting_guidelines}

IMPORTANT OUTPUT REQUIREMENTS:
1. DO NOT include a title in your response - only provide the article content
2. At the end, include a line with "HASHTAGS: " followed by 3-5 relevant hashtags separated by spaces (only if the article type supports hashtags)

INTERACTION MODEL:
The user will provide the files and a specific "Context Block" containing the Topic, Angle, and Audience. You will wait for this input, analyze the attached files based on those variables, and generate the {article_type.lower()}."""
    
    user_prompt = f"""{context_block}{additional_block}

Please analyze the following transcripts and generate a {article_type} based on the guidelines above:

{transcript_content}

Remember to:
1. Include the full {article_type.lower()} content (NO TITLE - title will be generated separately)
2. DO NOT include a references section - that will be generated separately
3. End with "HASHTAGS: " followed by 3-5 relevant hashtags (only if hashtags are appropriate for this article type)"""
    
    return system_instruction, user_prompt


def generate_article(transcripts, context_message, additional_info, article_type, word_count, audience, enable_research):
    """Generate article using Gemini API (without title and without references)."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")
    
    client = genai.Client(api_key=api_key)
    
    system_instruction, user_prompt = build_prompt(transcripts, context_message, additional_info, article_type, word_count, audience, enable_research)
    
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


def generate_title(article_content, article_type, audience, context_message):
    """Generate title for the article using a separate, simpler AI call."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")
    
    client = genai.Client(api_key=api_key)
    
    # Build context for title generation
    context_info = ""
    if context_message and context_message.strip():
        context_info = f"\nContext/Topic: {context_message}"
    
    system_instruction = f"""You are an expert at creating compelling, attention-grabbing titles for {article_type.lower()}s.

Your task is to generate a single, engaging title based on the article content provided.

Guidelines:
- The title should be concise (ideally 6-12 words, maximum 15 words)
- It should capture the main value proposition or key insight
- It should be optimized for the target audience: {audience}
- Make it compelling and click-worthy while remaining accurate
- Do not use quotes, colons, or special formatting unless necessary
- Return ONLY the title, nothing else"""

    user_prompt = f"""Based on the following {article_type.lower()} content, generate a compelling title.{context_info}

Target Audience: {audience}

Article Content:
{article_content}

Generate a single, compelling title (6-12 words, max 15 words):"""
    
    # Use a simpler model for title generation - no thinking, no research tools
    model = "gemini-2.0-flash-exp"  # Faster model for simple tasks
    
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=user_prompt),
            ],
        ),
    ]
    
    generate_content_config = types.GenerateContentConfig(
        # No thinking config - just normal LLM call
        # No tools - no Google Search
        system_instruction=[
            types.Part.from_text(text=system_instruction),
        ],
        max_output_tokens=50,  # Limit length - titles should be short
    )
    
    print("\n📝 Generating title...\n")
    
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=generate_content_config,
    )
    
    title = response.text.strip()
    
    # Clean up the title - remove quotes if present
    title = title.strip('"\'')
    
    print(f"✓ Title generated: {title}\n")
    
    return title


def generate_references(article_content, title, additional_info, article_type, audience):
    """Generate references section with verified links."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")
    
    client = genai.Client(api_key=api_key)
    
    # Extract links from additional_info
    provided_links = []
    if additional_info and additional_info.strip():
        provided_links = extract_links(additional_info)
    
    # Verify provided links
    verified_links = []
    if provided_links:
        print("\n🔍 Verifying provided links...")
        for link in provided_links:
            if verify_link(link):
                verified_links.append(link)
                print(f"  ✓ Verified: {link}")
            else:
                print(f"  ✗ Failed to verify: {link}")
    
    # Build context for references
    links_context = ""
    if verified_links:
        links_context = f"\n\nIMPORTANT: The following verified links were provided and should be prioritized in the references:\n" + "\n".join(f"- {link}" for link in verified_links)
    
    system_instruction = f"""You are an expert at creating reference sections for {article_type.lower()}s.

Your task is to generate a references section with 2-5 high-quality references based on the article content.

Guidelines:
- Generate 2-5 references (aim for 3-4 ideally)
- All links MUST be verified and accessible
- Include a mix of documentation, articles, research papers, or official resources
- Prioritize any verified links provided by the user
- Each reference should include: title/description and URL
- Format: [Title/Description](URL)
- Ensure all URLs are valid and accessible
- Target audience: {audience}
- Return ONLY the references section in markdown format, nothing else"""

    user_prompt = f"""Based on the following {article_type.lower()} content, generate a references section with 2-5 verified links.

Article Title: {title}
Target Audience: {audience}{links_context}

Article Content:
{article_content}

Generate a references section with 2-5 verified, accessible links. Format as markdown links: [Title](URL)"""
    
    # Use a simpler model for references generation - but allow URL context tool for verification
    model = "gemini-2.0-flash-exp"
    
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=user_prompt),
            ],
        ),
    ]
    
    # Use URL context tool to verify links
    generate_content_config = types.GenerateContentConfig(
        # No thinking config - just normal LLM call
        tools=[
            types.Tool(url_context=types.UrlContext()),  # Allow URL context for link verification
        ],
        system_instruction=[
            types.Part.from_text(text=system_instruction),
        ],
        max_output_tokens=500,  # Limit length for references section
    )
    
    print("\n📚 Generating references section...\n")
    
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=generate_content_config,
    )
    
    references_text = response.text.strip()
    
    # Extract all links from the references and verify them
    references_links = extract_links(references_text)
    print(f"\n🔍 Verifying {len(references_links)} reference links...")
    
    verified_references = []
    invalid_links = []
    
    for link in references_links:
        if verify_link(link):
            verified_references.append(link)
            print(f"  ✓ Verified: {link}")
        else:
            invalid_links.append(link)
            print(f"  ✗ Invalid link: {link}")
    
    if invalid_links:
        print(f"\n⚠️  Warning: {len(invalid_links)} invalid link(s) found. Regenerating references...")
        # Regenerate if there are invalid links
        user_prompt_retry = f"""The previous response contained invalid links. Please regenerate the references section with ONLY verified, accessible links.

Article Title: {title}
Target Audience: {audience}{links_context}

Article Content:
{article_content}

Generate a references section with 2-5 verified, accessible links. Format as markdown links: [Title](URL)
IMPORTANT: Only include links that you can verify are accessible."""
        
        contents_retry = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=user_prompt_retry),
                ],
            ),
        ]
        
        response_retry = client.models.generate_content(
            model=model,
            contents=contents_retry,
            config=generate_content_config,
        )
        
        references_text = response_retry.text.strip()
    
    print(f"\n✓ References section generated\n")
    
    return references_text


def parse_article_response(response):
    """Parse the response to extract content and hashtags (title is generated separately)."""
    content = response
    hashtags = []
    
    # Extract hashtags
    hashtags_match = re.search(r'HASHTAGS:\s*(.+?)$', response, re.MULTILINE | re.DOTALL)
    if hashtags_match:
        hashtags_text = hashtags_match.group(1).strip()
        hashtags = [tag.strip() for tag in hashtags_text.split() if tag.strip()]
        # Remove hashtags line from content
        content = re.sub(r'HASHTAGS:\s*.+?$', '', content, flags=re.MULTILINE | re.DOTALL).strip()
    
    return content, hashtags


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


def get_unique_filepath(articles_dir, base_filename):
    """Get a unique filepath, appending number if file exists."""
    filepath = articles_dir / f"{base_filename}.md"
    counter = 1
    while filepath.exists():
        filepath = articles_dir / f"{base_filename}_{counter}.md"
        counter += 1
    return filepath


def format_error_message(error):
    """Format better error messages for common issues."""
    error_msg = str(error).lower()
    
    if "api key" in error_msg or "gemini_api_key" in error_msg or "authentication" in error_msg:
        return "❌ Error: Invalid or missing GEMINI_API_KEY. Please check your API key configuration."
    elif "quota" in error_msg or "rate limit" in error_msg or "429" in error_msg:
        return "❌ Error: API quota exceeded or rate limit reached. Please try again later."
    elif "permission" in error_msg or "403" in error_msg:
        return "❌ Error: Permission denied. Check your API key permissions."
    elif "not found" in error_msg or "404" in error_msg:
        return "❌ Error: Resource not found. Check your YouTube URLs or API endpoints."
    elif "timeout" in error_msg or "timed out" in error_msg:
        return "❌ Error: Request timed out. The operation took too long. Please try again."
    elif "network" in error_msg or "connection" in error_msg:
        return "❌ Error: Network connection issue. Please check your internet connection."
    elif "transcript" in error_msg or "youtube" in error_msg:
        return f"❌ Error: {error}"
    else:
        return f"❌ Error: {error}"


def main():
    parser = argparse.ArgumentParser(description='Generate article/post from YouTube transcripts')
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
    parser.add_argument('--additional-info', default='', help='Additional information about the subject (can include links) (optional)')
    parser.add_argument('--article-type', default='LinkedIn Article', 
                       choices=['LinkedIn Article', 'LinkedIn Post', 'Substack', 'Reddit Post', 'Blog Post', 'Twitter Thread'],
                       help='Type of article/post to generate (default: LinkedIn Article)')
    parser.add_argument('--word-count', default='1000', 
                       choices=['500', '1000', '1500', '2000', '2500', '3000'],
                       help='Target word count (default: 1000)')
    parser.add_argument('--audience', default='Senior engineers and technical practitioners',
                       help='Target audience (default: Senior engineers and technical practitioners)')
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
        print("❌ Error: At least one YouTube URL is required", file=sys.stderr)
        sys.exit(1)
    
    print(f"📹 Processing {len(urls)} YouTube video(s)...\n")
    
    # Progress indicator: Step 1/4
    print("📊 Progress: [1/4] Downloading transcripts...\n")
    
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
        print("❌ Error: No transcripts were successfully downloaded", file=sys.stderr)
        sys.exit(1)
    
    print(f"\n✓ Successfully downloaded {len(transcripts)} transcript(s)\n")
    
    # Progress indicator: Step 2/4
    print("📊 Progress: [2/4] Generating article content...\n")
    
    # Generate article (without title and without references)
    try:
        article_response = generate_article(
            transcripts,
            args.context,
            args.additional_info,
            args.article_type,
            args.word_count,
            args.audience,
            args.enable_research
        )
    except Exception as e:
        print(format_error_message(e), file=sys.stderr)
        sys.exit(1)
    
    # Parse article response
    content, hashtags = parse_article_response(article_response)
    
    # Progress indicator: Step 3/4
    print("📊 Progress: [3/4] Generating title...\n")
    
    # Generate title separately
    try:
        title = generate_title(content, args.article_type, args.audience, args.context)
    except Exception as e:
        print(format_error_message(e), file=sys.stderr)
        # Fallback to default title if title generation fails
        title = f"{args.article_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"⚠️  Using fallback title: {title}")
    
    # Progress indicator: Step 4/4
    print("📊 Progress: [4/4] Generating references...\n")
    
    # Generate references separately
    try:
        references = generate_references(content, title, args.additional_info, args.article_type, args.audience)
    except Exception as e:
        print(format_error_message(e), file=sys.stderr)
        # Fallback to empty references if generation fails
        references = "\n\n## References\n\n*References could not be generated.*"
        print(f"⚠️  Using fallback references section")
    
    # Create articles directory
    articles_dir = Path("articles")
    articles_dir.mkdir(exist_ok=True)
    
    # Save article with unique filename
    filename = sanitize_filename(title)
    filepath = get_unique_filepath(articles_dir, filename)
    
    # Build metadata
    metadata = f"""---
title: {title}
article_type: {args.article_type}
word_count_target: {args.word_count}
audience: {args.audience}
generated_date: {datetime.now().isoformat()}
source_videos: {len(urls)}
video_ids: {', '.join(video_ids)}
research_enabled: {args.enable_research}
---

"""
    
    # Format the article with metadata, title, content, references, and hashtags
    article_content = metadata + f"# {title}\n\n"
    article_content += content
    article_content += f"\n\n---\n\n## References\n\n{references}"
    if hashtags:
        article_content += f"\n\n---\n\n**Hashtags:** {' '.join(hashtags)}\n"
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(article_content)
    
    print(f"\n✓ Article saved to: {filepath}")
    if filepath.name != f"{filename}.md":
        print(f"  Note: Filename adjusted to avoid duplicates")
    print(f"  Title: {title}")
    print(f"  References: {len(extract_links(references))} link(s)")
    print(f"  Hashtags: {', '.join(hashtags) if hashtags else 'None'}")


if __name__ == '__main__':
    main()
