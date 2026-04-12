"""
YouTube to MP3 Downloader
-------------------------
Downloads the audio from a YouTube video and saves it as an MP3 file.

Requirements:
    pip install yt-dlp
    ffmpeg must be installed on the system

Usage:
    from youtube_to_mp3 import download_audio

    # Download to the default 'downloads' subfolder
    filepath = download_audio("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    # Or run this file directly
    python youtube_to_mp3.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
"""

import os
import sys
from typing import Optional
import yt_dlp


def download_audio(url: str, output_dir: Optional[str] = None, quality: str = "192") -> str:
    """
    Download audio from a YouTube URL and save it as an MP3 file.

    Args:
        url: A YouTube video URL.
        output_dir: Directory to save the MP3 into. Defaults to a 'downloads'
                    subfolder next to this script.
        quality: MP3 bitrate in kbps (e.g. "128", "192", "320").

    Returns:
        The absolute path to the downloaded MP3 file.
    """
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")

    os.makedirs(output_dir, exist_ok=True)

    # We'll capture the final filename via a progress hook
    result = {"filepath": None}

    def _progress_hook(d):
        if d["status"] == "finished":
            print(f"Download complete, converting to MP3 ...")

    def _postprocessor_hook(d):
        if d["status"] == "finished":
            result["filepath"] = d["info_dict"].get("filepath")

    options = {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": quality,
            }
        ],
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "progress_hooks": [_progress_hook],
        "postprocessor_hooks": [_postprocessor_hook],
        "quiet": False,
        "no_warnings": False,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        print(f"Fetching: {url}")
        ydl.download([url])

    if result["filepath"]:
        print(f"Saved to: {result['filepath']}")
    return result["filepath"]


# ---------------------------------------------------------------------------
# Run directly from the command line
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python youtube_to_mp3.py <YouTube-URL>")
        sys.exit(1)

    path = download_audio(sys.argv[1])
    if path:
        print(f"\nDone! File saved at:\n  {path}")
    else:
        print("\nSomething went wrong — no file was saved.")
        sys.exit(1)
