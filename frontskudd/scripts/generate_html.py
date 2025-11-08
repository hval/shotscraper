#!/usr/bin/env python3
"""
Refactored HTML generator for news timelapse viewer.
Generates a modern, responsive web interface for viewing timelapse videos.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
import html
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class VideoInfo:
    """Information about a video file."""
    group: str
    date: str
    video_path: Path
    metadata_path: Path
    title: str = ""

    @property
    def relative_video_path(self) -> str:
        """Get video path relative to output directory."""
        return f"videos/{self.video_path.name}"

    @property
    def relative_metadata_path(self) -> str:
        """Get metadata path relative to output directory."""
        return f"metadata/{self.metadata_path.name}"

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "group": self.group,
            "video": self.relative_video_path,
            "metadata": self.relative_metadata_path
        }
        if self.title:
            result["title"] = self.title
        return result


class VideoCollector:
    """Collects and organizes video files and metadata."""

    def __init__(self, video_dir: Path, metadata_dir: Path, config_path: Path = None):
        self.video_dir = video_dir
        self.metadata_dir = metadata_dir
        self.config = self._load_config(config_path) if config_path else {}

    def _load_config(self, config_path: Path) -> Dict:
        """Load configuration to get video titles."""
        try:
            import yaml
            with open(config_path, "r") as f:
                return yaml.safe_load(f)
        except Exception:
            return {}

    def collect_videos(self) -> Dict[str, List[VideoInfo]]:
        """Collect all videos grouped by date."""
        videos = sorted(self.video_dir.glob("*.mp4"))
        archive = {}

        for video in videos:
            video_info = self._parse_video_filename(video)
            if video_info:
                archive.setdefault(video_info.date, []).append(video_info)

        return archive

    def _parse_video_filename(self, video_path: Path) -> Optional[VideoInfo]:
        """Parse video filename to extract group and date."""
        match = re.match(r"(.+)-(\d{4}-\d{2}-\d{2})\.mp4", video_path.name)
        if not match:
            logger.warning(f"Could not parse video filename: {video_path.name}")
            return None

        group_name, date_str = match.groups()
        metadata_path = self.metadata_dir / f"metadata-{group_name}-{date_str}.json"

        # Check if metadata exists
        if not metadata_path.exists():
            logger.warning(f"Missing metadata file: {metadata_path}")

        # Find title from config
        title = self._get_title_for_group(group_name)

        return VideoInfo(
            group=group_name,
            date=date_str,
            video_path=video_path,
            metadata_path=metadata_path,
            title=title
        )

    def _get_title_for_group(self, group_name: str) -> str:
        """Get human-friendly title for a video group."""
        videos = self.config.get("videos", [])
        for video_config in videos:
            if video_config.get("name") == group_name:
                return video_config.get("title", group_name)
        return group_name


class HTMLTemplate:
    """Manages HTML template generation."""

    @staticmethod
    def get_css() -> str:
        """Get CSS styles."""
        return """
        :root {
            --primary-color: #222;
            --secondary-color: #f9f9f9;
            --accent-color: #007acc;
            --text-color: #333;
            --border-radius: 12px;
            --shadow: 0 0 8px rgba(0,0,0,0.1);
        }

        * {
            box-sizing: border-box;
        }

        body {
            font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
            margin: 0;
            padding: 0;
            background: var(--secondary-color);
            color: var(--text-color);
            line-height: 1.5;
        }

        header {
            background: var(--primary-color);
            color: white;
            padding: 1em;
            box-shadow: var(--shadow);
        }

        .header-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 1em;
            margin-bottom: 1em;
        }

        h1 {
            margin: 0;
            font-size: 1.4em;
            font-weight: 600;
        }

        .day-selector {
            position: relative;
            display: inline-block;
        }

        .day-button {
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: 2px solid rgba(255, 255, 255, 0.3);
            padding: 0.75em 1.5em;
            font-size: 1.4em;
            font-weight: 700;
            border-radius: 8px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 0.5em;
            transition: all 0.2s ease;
            min-width: 150px;
            justify-content: center;
        }

        .day-button:hover {
            background: rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.5);
        }

        .day-button.open {
            background: rgba(255, 255, 255, 0.3);
            border-bottom-left-radius: 0;
            border-bottom-right-radius: 0;
        }

        .day-button .arrow {
            font-size: 0.8em;
            transition: transform 0.2s ease;
        }

        .day-button.open .arrow {
            transform: rotate(180deg);
        }

        .day-dropdown {
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            background: white;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-top: none;
            border-bottom-left-radius: 8px;
            border-bottom-right-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            z-index: 1000;
            display: none;
            max-height: 300px;
            overflow-y: auto;
        }

        .day-dropdown.open {
            display: block;
        }

        .day-option {
            padding: 0.75em 1em;
            color: var(--text-color);
            cursor: pointer;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background-color 0.2s ease;
        }

        .day-option:hover {
            background: #f5f5f5;
        }

        .day-option:last-child {
            border-bottom: none;
        }

        .day-option .day-name {
            font-weight: 600;
        }

        .day-option .day-date {
            font-size: 0.9em;
            color: #666;
        }

        .description {
            text-align: center;
            font-size: 0.9em;
            opacity: 0.9;
            margin: 0;
            background: rgba(255, 255, 255, 0.2);
            padding: 0.75em 1.5em;
            border-radius: 8px;
        }

        .header-controls {
            display: flex;
            align-items: center;
            gap: 1em;
            flex-wrap: wrap;
        }

        select {
            font-size: 1em;
            padding: 0.5em;
            border: none;
            border-radius: 6px;
            background: white;
            color: var(--text-color);
            cursor: pointer;
        }

        select:focus {
            outline: 2px solid var(--accent-color);
        }

        main {
            padding: 1em;
            max-width: 1200px;
            margin: 0 auto;
        }

        .loading {
            text-align: center;
            padding: 2em;
            color: #666;
        }

        .loading::after {
            content: '';
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid #ccc;
            border-top: 2px solid var(--accent-color);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-left: 0.5em;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .video-block {
            background: white;
            padding: 1.5em;
            margin-bottom: 2em;
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            transition: transform 0.2s ease;
        }

        .video-block:hover {
            transform: translateY(-2px);
        }

        .video-block h2 {
            margin: 0 0 1em 0;
            color: var(--primary-color);
            font-size: 1.2em;
            border-bottom: 2px solid var(--accent-color);
            padding-bottom: 0.5em;
        }

        video {
            width: 100%;
            border-radius: 8px;
            margin-bottom: 1em;
            background: #000;
        }

        .search-container {
            margin-bottom: 1em;
            position: relative;
        }

        .search-input {
            width: 100%;
            font-size: 1em;
            padding: 0.75em;
            border: 2px solid #ddd;
            border-radius: 8px;
            transition: border-color 0.2s ease;
        }

        .search-input:focus {
            outline: none;
            border-color: var(--accent-color);
        }

        .search-input::placeholder {
            color: #999;
        }

        .results {
            font-size: 0.9em;
            line-height: 1.6;
            background: #f8f9fa;
            padding: 1em;
            border-radius: 8px;
            border: 1px solid #e9ecef;
            max-height: 300px;
            overflow-y: auto;
            word-wrap: break-word;
        }

        .results:empty::before {
            content: 'Ingen tekst tilgjengelig';
            color: #666;
            font-style: italic;
        }

        .results hr {
            border: none;
            border-top: 1px solid #ddd;
            margin: 1em 0;
        }

        .results strong {
            color: var(--accent-color);
            font-weight: 600;
        }

        .search-result-item {
            padding: 0.75em;
            margin: 0.5em 0;
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s ease;
            position: relative;
        }

        .search-result-item:hover {
            background: #f0f8ff;
            border-color: var(--accent-color);
            transform: translateY(-1px);
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        .search-result-item:active {
            transform: translateY(0);
        }

        .timestamp-info {
            color: var(--accent-color);
            font-size: 0.85em;
            font-weight: 600;
            margin-bottom: 0.5em;
            display: flex;
            align-items: center;
            gap: 0.5em;
        }


        .no-results {
            text-align: center;
            color: #666;
            font-style: italic;
            padding: 2em;
        }

        .error {
            background: #fff5f5;
            border: 1px solid #fed7d7;
            color: #c53030;
            padding: 1em;
            border-radius: 8px;
            margin: 1em 0;
        }

        /* Mobile responsiveness */
        @media (max-width: 768px) {
            header {
                flex-direction: column;
                text-align: center;
            }

            main {
                padding: 0.5em;
            }

            .video-block {
                padding: 1em;
                margin-bottom: 1em;
            }

            h1 {
                font-size: 1.2em;
            }

            .search-input {
                font-size: 16px; /* Prevent zoom on iOS */
            }
        }

        /* Dark mode support */
        @media (prefers-color-scheme: dark) {
            :root {
                --secondary-color: #1a1a1a;
                --text-color: #e0e0e0;
            }

            .video-block {
                background: #2d2d2d;
                color: var(--text-color);
            }

            .results {
                background: #3d3d3d;
                border-color: #4d4d4d;
                color: var(--text-color);
            }

            .search-input {
                background: #3d3d3d;
                color: var(--text-color);
                border-color: #4d4d4d;
            }
        }
        """

    @staticmethod
    def get_javascript() -> str:
        """Get JavaScript code."""
        return """
        class FrontskuddApp {
            constructor(archive) {
                this.archive = archive;
                this.contentEl = document.getElementById('content');
                this.dayButton = document.getElementById('day-button');
                this.dayDropdown = document.getElementById('day-dropdown');
                this.currentDaySpan = document.getElementById('current-day');
                this.currentDate = null;
                this.isDropdownOpen = false;

                this.init();
            }

            init() {
                // Setup dropdown functionality
                this.setupDropdown();

                // Load latest date
                const dates = Object.keys(this.archive).sort().reverse();
                if (dates.length > 0) {
                    this.populateDropdown(dates);
                    this.selectDate(dates[0]);
                }

                // Close dropdown when clicking outside
                document.addEventListener('click', (e) => {
                    if (!this.dayButton.contains(e.target) && !this.dayDropdown.contains(e.target)) {
                        this.closeDropdown();
                    }
                });
            }

            setupDropdown() {
                this.dayButton.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.toggleDropdown();
                });
            }

            populateDropdown(dates) {
                this.dayDropdown.innerHTML = '';

                dates.forEach(dateString => {
                    const option = document.createElement('div');
                    option.className = 'day-option';
                    option.dataset.date = dateString;

                    const dayName = this.getDayName(dateString);
                    const formattedDate = this.formatDate(dateString);

                    option.innerHTML = `
                        <span class="day-name">${dayName}</span>
                        <span class="day-date">${formattedDate}</span>
                    `;

                    option.addEventListener('click', () => {
                        this.selectDate(dateString);
                        this.closeDropdown();
                    });

                    this.dayDropdown.appendChild(option);
                });
            }

            toggleDropdown() {
                this.isDropdownOpen = !this.isDropdownOpen;
                this.dayButton.classList.toggle('open', this.isDropdownOpen);
                this.dayDropdown.classList.toggle('open', this.isDropdownOpen);
            }

            closeDropdown() {
                this.isDropdownOpen = false;
                this.dayButton.classList.remove('open');
                this.dayDropdown.classList.remove('open');
            }

            selectDate(dateString) {
                this.currentDate = dateString;
                const dayName = this.getDayName(dateString);
                this.currentDaySpan.textContent = dayName;
                this.loadVideos(dateString);
            }

            formatDate(dateString) {
                try {
                    const date = new Date(dateString + 'T12:00:00');
                    return date.toLocaleDateString('no-NO', {
                        day: 'numeric',
                        month: 'short'
                    });
                } catch (e) {
                    return dateString;
                }
            }

            getDayName(dateString) {
                // Norwegian day names
                const dayNames = ['Søndag', 'Mandag', 'Tirsdag', 'Onsdag', 'Torsdag', 'Fredag', 'Lørdag'];

                try {
                    const date = new Date(dateString + 'T12:00:00'); // Add time to avoid timezone issues
                    return dayNames[date.getDay()];
                } catch (e) {
                    return dateString;
                }
            }

            async loadVideos(date) {
                this.contentEl.innerHTML = '<div class="loading">Laster videoer...</div>';

                const dayVideos = this.archive[date] || [];

                if (dayVideos.length === 0) {
                    this.contentEl.innerHTML = '<div class="no-results">Ingen videoer funnet for denne datoen.</div>';
                    return;
                }

                this.contentEl.innerHTML = '';

                for (const video of dayVideos) {
                    await this.createVideoBlock(video);
                }
            }

            async createVideoBlock(videoInfo) {
                const block = document.createElement('div');
                block.className = 'video-block';
                block.innerHTML = this.getVideoBlockHTML(videoInfo);

                this.contentEl.appendChild(block);

                // Load metadata and setup search
                try {
                    await this.setupVideoBlock(block, videoInfo);
                } catch (error) {
                    console.error('Failed to load metadata:', error);
                    this.showError(block, 'Kunne ikke laste metadata');
                }
            }

            getVideoBlockHTML(videoInfo) {
                return `
                    <h2>${this.escapeHtml(videoInfo.title || videoInfo.group)}</h2>
                    <video controls preload="auto">
                        <source src="${this.escapeHtml(videoInfo.video)}" type="video/mp4">
                        Din nettleser støtter ikke video-avspilling.
                    </video>
                    <div class="search-container">
                        <input type="search" class="search-input" placeholder="Søk i toppsaker fra ${this.escapeHtml(videoInfo.title || videoInfo.group)}..." />
                    </div>
                    <div class="results" data-group="${this.escapeHtml(videoInfo.group)}">Laster tekst...</div>
                `;
            }

            async setupVideoBlock(block, videoInfo) {
                const resultsEl = block.querySelector('.results');
                const searchInput = block.querySelector('.search-input');

                // Load metadata
                const response = await fetch(videoInfo.metadata);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const metadata = await response.json();

                // video_time now contains the correct cumulative timestamps from video generation
                // No need for additional calculations

                // Display latest frame by default
                this.displayLatestFrame(resultsEl, metadata);

                // Setup search
                this.setupSearch(searchInput, resultsEl, metadata);
            }


            displayLatestFrame(resultsEl, metadata) {
                if (!metadata || metadata.length === 0) {
                    resultsEl.innerHTML = '<div class="no-results">Ingen tekst tilgjengelig</div>';
                    return;
                }

                const lastFrame = metadata[metadata.length - 1];
                const snippet = this.formatFrameText(lastFrame, false);
                resultsEl.innerHTML = snippet || '<div class="no-results">Ingen tekst i siste frame</div>';
            }

            setupSearch(searchInput, resultsEl, metadata) {
                let searchTimeout;

                searchInput.addEventListener('input', (e) => {
                    clearTimeout(searchTimeout);

                    searchTimeout = setTimeout(() => {
                        const term = e.target.value.toLowerCase().trim();

                        if (!term) {
                            this.displayLatestFrame(resultsEl, metadata);
                            return;
                        }

                        this.performSearch(resultsEl, metadata, term);
                    }, 300); // Debounce search
                });
            }

            performSearch(resultsEl, metadata, term) {
                const matches = metadata.filter(frame =>
                    this.frameContainsText(frame, term)
                );

                if (matches.length === 0) {
                    resultsEl.innerHTML = '<div class="no-results">Ingen treff funnet</div>';
                    return;
                }

                const resultsHTML = matches
                    .map(frame => this.formatFrameText(frame, true))
                    .filter(text => text)
                    .join('<hr>');

                resultsEl.innerHTML = resultsHTML || '<div class="no-results">Ingen tekst i resultater</div>';

                // Add click handlers for search results
                this.addClickHandlers(resultsEl, matches);
            }

            frameContainsText(frame, term) {
                return Object.entries(frame).some(([key, value]) => {
                    if (this.isMetadataField(key)) return false;
                    return typeof value === 'string' && value.toLowerCase().includes(term);
                });
            }

            formatFrameText(frame, isClickable = false) {
                const textEntries = Object.entries(frame)
                    .filter(([key]) => !this.isMetadataField(key))
                    .filter(([, value]) => typeof value === 'string' && value.trim())
                    .map(([key, value]) => `<strong>${this.escapeHtml(key)}:</strong> ${this.escapeHtml(value)}`);

                const content = textEntries.join('\\n\\n');

                if (isClickable && frame.video_time !== undefined) {
                    const videoTimestamp = this.formatVideoTime(frame.video_time);
                    // Extract burnt-in timestamp from frame metadata (if available)
                    const burntInTime = this.extractBurntInTimestamp(frame);
                    const displayTime = burntInTime ? `${burntInTime} (${videoTimestamp})` : `${videoTimestamp} (Frame ${frame.frame_index + 1})`;

                    return `<div class="search-result-item" data-video-time="${frame.video_time}" data-frame-index="${frame.frame_index}">
                        <div class="timestamp-info">🕐 ${displayTime}</div>
                        ${content}
                    </div>`;
                }

                return content;
            }

            formatVideoTime(seconds) {
                const minutes = Math.floor(seconds / 60);
                const remainingSeconds = Math.floor(seconds % 60);
                return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
            }

            extractBurntInTimestamp(frame) {
                // The burnt-in timestamp should be stored in frame metadata
                // If not available, we'll need to calculate it from commit data
                if (frame.burnt_in_time) {
                    return frame.burnt_in_time;
                }

                // For now, return null - this will need to be populated by the video generation script
                // The video generation should include the actual Oslo time when the screenshot was taken
                return null;
            }

            addClickHandlers(resultsEl, matches) {
                const videoBlock = resultsEl.closest('.video-block');
                const video = videoBlock.querySelector('video');

                resultsEl.querySelectorAll('.search-result-item').forEach((item, index) => {
                    item.addEventListener('click', () => {
                        const videoTime = parseFloat(item.dataset.videoTime);
                        const frameIndex = parseInt(item.dataset.frameIndex);

                        if (!isNaN(videoTime) && video) {
                            video.currentTime = videoTime;
                            video.scrollIntoView({ behavior: 'smooth', block: 'center' });

                            // Optional: play video briefly to show the frame
                            video.play();
                            setTimeout(() => video.pause(), 1000);
                        }
                    });
                });
            }

            isMetadataField(key) {
                return ['frame_index', 'video_time', 'frame_path', 'video_name', 'burnt_in_time'].includes(key);
            }

            showError(block, message) {
                const resultsEl = block.querySelector('.results');
                resultsEl.innerHTML = `<div class="error">${this.escapeHtml(message)}</div>`;
            }

            escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
        }

        // Initialize app when DOM is loaded
        document.addEventListener('DOMContentLoaded', () => {
            new FrontskuddApp(window.ARCHIVE_DATA);
        });
        """

    def generate_html(self, archive: Dict[str, List[VideoInfo]], latest_date: str, config_description: str = "") -> str:
        """Generate complete HTML document."""
        # Prepare data for JavaScript
        archive_data = {
            date: [video.to_dict() for video in videos]
            for date, videos in archive.items()
        }

        # Add video titles to the archive data
        for date, videos in archive.items():
            for i, video_info in enumerate(videos):
                if hasattr(video_info, 'title'):
                    archive_data[date][i]['title'] = video_info.title

        # Get sorted dates for JavaScript
        dates = sorted(archive.keys(), reverse=True)

        return f"""<!DOCTYPE html>
<html lang="no">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📰 Frontskudd - Nyhetsfront Timelapse</title>
    <meta name="description" content="{html.escape(config_description or 'Se hvordan norske nyhetssider endrer seg gjennom dagen')}">
    <style>{self.get_css()}</style>
</head>
<body>
    <header>
        <div class="header-top">
            <h1>📰 Frontskudd</h1>
            <div class="header-controls">
                <div class="day-selector">
                    <div class="day-button" id="day-button">
                        <span id="current-day">Laster...</span>
                        <span class="arrow">▼</span>
                    </div>
                    <div class="day-dropdown" id="day-dropdown">
                        <!-- Options will be populated by JavaScript -->
                    </div>
                </div>
            </div>
        </div>
        <p class="description">{html.escape(config_description)}</p>
    </header>

    <main>
        <div id="content">
            <div class="loading">Laster...</div>
        </div>
    </main>

    <script>
        // Archive data
        window.ARCHIVE_DATA = {json.dumps(archive_data, indent=2, ensure_ascii=False)};

        // Application code
        {self.get_javascript()}
    </script>
</body>
</html>"""


class HTMLGenerator:
    """Main HTML generator class."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.out_dir = base_dir / "out"
        self.video_dir = self.out_dir / "videos"
        self.metadata_dir = self.out_dir / "metadata"
        self.html_file = self.out_dir / "index.html"

    def generate(self) -> bool:
        """Generate the HTML file."""
        try:
            # Load config
            config_path = self.base_dir / "config.yaml"

            # Collect videos with config
            collector = VideoCollector(self.video_dir, self.metadata_dir, config_path)
            archive = collector.collect_videos()

            if not archive:
                logger.error("No videos found in videos directory")
                return False

            # Get description from config
            config_description = collector.config.get("description", "")

            # Find latest date
            dates = sorted(archive.keys(), reverse=True)
            latest_date = dates[0]

            logger.info(f"Found {len(archive)} dates with {sum(len(videos) for videos in archive.values())} total videos")

            # Generate HTML
            template = HTMLTemplate()
            html_content = template.generate_html(archive, latest_date, config_description)

            # Write file
            self.html_file.write_text(html_content, encoding="utf-8")
            logger.info(f"HTML generated: {self.html_file}")

            return True

        except Exception as e:
            logger.error(f"Failed to generate HTML: {e}")
            return False


def main():
    """Main entry point."""
    base_dir = Path(__file__).resolve().parent.parent
    generator = HTMLGenerator(base_dir)

    if generator.generate():
        print(f"✅ HTML generated: {generator.html_file}")
    else:
        print("❌ HTML generation failed")
        exit(1)


if __name__ == "__main__":
    main()