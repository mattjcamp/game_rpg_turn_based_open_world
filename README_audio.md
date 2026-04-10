# YouTube to MP3 Downloader

A simple Python script that downloads the audio from a YouTube video and saves it as an MP3 file.

## Requirements

- **Python 3.10+**
- **yt-dlp** — handles the YouTube download
- **FFmpeg** — handles the audio conversion to MP3

## Installation

Install the Python dependency:

```bash
pip3 install yt-dlp
```

> **Note:** If `pip3` is not found either, use `python3 -m pip install yt-dlp` instead.

Install FFmpeg:

```bash
# macOS (Homebrew)
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg

# Windows (Chocolatey)
choco install ffmpeg
```

## Usage

### Command line

```bash
python3 youtube_to_mp3.py "https://www.youtube.com/watch?v=VIDEO_ID"

python3 youtube_to_mp3.py "https://youtu.be/NwpQQl8ZERQ"


```

### As a Python import

```python
from youtube_to_mp3 import download_audio

filepath = download_audio("https://www.youtube.com/watch?v=VIDEO_ID")
```

### Parameters

The `download_audio` function accepts three arguments:

| Parameter    | Type         | Default                              | Description                                    |
|--------------|--------------|--------------------------------------|------------------------------------------------|
| `url`        | `str`        | *(required)*                         | A YouTube video URL                            |
| `output_dir` | `str | None` | `downloads/` subfolder next to script | Directory where the MP3 will be saved          |
| `quality`    | `str`        | `"192"`                              | MP3 bitrate in kbps (`"128"`, `"192"`, `"320"`) |

### Examples

Download with default settings (192 kbps, saved to `downloads/`):

```python
download_audio("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
```

Download at 320 kbps to a custom folder:

```python
download_audio(
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    output_dir="/path/to/my/music",
    quality="320",
)
```

## Output

Downloaded MP3 files are saved to a `downloads/` subfolder by default. The filename is derived from the video title on YouTube.
