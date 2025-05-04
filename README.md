# Pinterest Board Downloader

A powerful tool to download all images from Pinterest boards or any other web page with dynamically loaded content.

## Features

- **Smart Pinterest Detection**: Automatically stops scrolling once the "More ideas" section appears
- **Exclusion Filtering**: Excludes images from the "More ideas" section to focus only on board content
- **High Resolution Support**: Captures both `src` and `srcset` image URLs to get the highest quality versions
- **Quality Control Options**: Flexible control over image quality preferences for downloads
- **Dynamic Content Handling**: Uses Selenium to scroll and capture images as they load
- **Headless Operation**: Runs Firefox in headless mode for efficiency
- **Duplicate Prevention**: Uses MD5 hashing to ensure unique filenames
- **Progress Feedback**: Provides real-time progress updates during scrolling and downloading

## Installation

### Prerequisites

- Python 3.7 or later
- Firefox browser (required for Selenium WebDriver)

### Using uv (Recommended)

[uv](https://github.com/astral-sh/uv) is a fast Python package installer and resolver. To install dependencies with uv:

```bash
# Install uv if you don't have it yet
pip install uv

# Clone the repository
git clone https://github.com/yourusername/pinterest-board-downloader.git
cd pinterest-board-downloader

# Create and activate a virtual environment with uv
uv venv

# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies with uv
uv pip install selenium webdriver-manager requests
```

### Manual Installation (Alternative)

If you prefer not to use uv:

```bash
# Clone the repository
git clone https://github.com/yourusername/pinterest-board-downloader.git
cd pinterest-board-downloader

# Create and activate a virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install required packages
pip install selenium webdriver-manager requests
```

## Usage

### Basic Usage

```bash
python download_images.py https://www.pinterest.com/username/boardname/
```

This will download all images from the specified Pinterest board to a folder named `images` in the current directory.

### Advanced Options

```bash
python download_images.py https://www.pinterest.com/username/boardname/ --output-dir my_pinterest_images --scroll-pause 3.5 --quality prioritize-high
```

## Command-Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `url` | URL of the Pinterest board or web page (required) | None |
| `--output-dir` | Directory to save downloaded images | `images` |
| `--scroll-pause` | Time to wait between scrolls (seconds) | `2.0` |
| `--quality` | Image quality preference (options: high-only, prioritize-high, all) | `high-only` |

### Quality Options Explained

- **high-only**: Only download high-quality images (ignores lower quality versions)
- **prioritize-high**: Download high-quality images when available, fall back to lower quality if high-quality isn't available
- **all**: Download both high and low quality versions of each image (adds quality suffix to filenames)

## How It Works

1. **Browser Initialization**: Launches Firefox in headless mode using Selenium WebDriver
2. **Scrolling & Collection**:
   - Scrolls to the bottom of the page at regular intervals
   - Collects image URLs as they appear during scrolling
   - Monitors for the appearance of Pinterest's "More ideas" section
   - Stops scrolling when "More ideas" appears or no new content loads
3. **Image Download**:
   - Processes collected URLs to remove duplicates
   - Creates the output directory if it doesn't exist
   - Downloads each image with proper error handling
   - Names files using MD5 hash of the source URL to prevent duplicates
   - Preserves original file extensions when possible

## Technical Details

### Scrolling Logic

The script uses JavaScript execution to scroll to the bottom of the page and waits for a specified amount of time for content to load before collecting new images. It detects the end of relevant content by:

1. Identifying Pinterest's "More ideas" container through its data-test-id attribute
2. Comparing page height before and after scrolling to detect when no new content loads

### Image URL Collection

Images are collected from two HTML attributes:

- `src`: The primary image source
- `srcset`: Contains multiple image sources for different resolutions

### Filename Generation

To ensure uniqueness while preserving file types:

1. Computes MD5 hash of the full image URL
2. Extracts file extension from original URL path
3. Uses `.jpg` as fallback extension if original is missing or invalid
4. Combines hash and extension to form the filename

## Limitations and Notes

- **Pinterest Account**: You don't need to be logged in to download public boards
- **Firefox Required**: The script uses Firefox WebDriver (geckodriver)
- **Rate Limiting**: Pinterest may rate-limit or block IPs that make too many requests
- **Dynamic Content**: Since the tool depends on Pinterest's DOM structure, it may need updates if Pinterest changes their website design
- **Ethical Usage**: Only use this tool on content you have legal rights to download
- **Private Boards**: Cannot access private boards without authentication

## Troubleshooting

### Common Issues

#### WebDriver Installation Fails

```text
Error: GeckoDriver installation failed
```

**Solution**: Manually install geckodriver:

1. Download from [Mozilla's GitHub](https://github.com/mozilla/geckodriver/releases)
2. Add to your system PATH or place in the script directory

#### No Images Downloaded

**Possible causes**:

- URL format is incorrect
- Board is private/restricted
- Pinterest has changed its DOM structure

**Solution**:

- Verify the board URL works in a browser
- Check the board is public
- Update the script's selectors if Pinterest's layout has changed

#### Slow Downloads

**Solution**: Adjust the `--scroll-pause` parameter to find an optimal balance between speed and completeness. Decrease for faster execution, increase for more thorough collection.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [Selenium](https://selenium.dev/) for browser automation
- [webdriver-manager](https://github.com/SergeyPirogov/webdriver_manager) for easy WebDriver setup
- [requests](https://requests.readthedocs.io/) for handling HTTP requests
