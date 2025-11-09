#!/usr/bin/env python3
"""
Refactored news timelapse video generator.
Generates time-lapse videos from website screenshots stored in git commits.
"""

import os
import subprocess
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Iterator
import yaml
import pytesseract
from PIL import Image, ImageFile, ImageDraw, ImageFont
import argparse
import tempfile
import shutil
import zoneinfo

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ImageFile.LOAD_TRUNCATED_IMAGES = True


@dataclass
class VideoConfig:
    """Configuration for video generation."""
    archive_days: int = 7
    speedup_factor: int = 300
    description: str = ""
    video_groups: List[Dict] = field(default_factory=list)
    site_crop_top: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, file_path: Path) -> 'VideoConfig':
        """Load configuration from YAML file."""
        try:
            with open(file_path, "r") as f:
                data = yaml.safe_load(f)

            return cls(
                archive_days=data.get("archive_days", 7),
                speedup_factor=data.get("speedup_factor", 300),
                description=data.get("description", ""),
                video_groups=data.get("videos", []),
                site_crop_top=data.get("site_crop_top", {})
            )
        except Exception as e:
            logger.error(f"Failed to load config from {file_path}: {e}")
            return cls()


class FontManager:
    """Manages font loading across different platforms."""

    _font_cache: Dict[int, ImageFont.ImageFont] = {}

    FONT_PATHS = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
        "/System/Library/Fonts/Helvetica.ttc",  # macOS
        "C:/Windows/Fonts/arial.ttf",  # Windows
    ]

    @classmethod
    def get_font(cls, size: int = 36) -> ImageFont.ImageFont:
        """Get font with specified size, using cache."""
        if size in cls._font_cache:
            return cls._font_cache[size]

        font = cls._load_font(size)
        cls._font_cache[size] = font
        return font

    @classmethod
    def _load_font(cls, size: int) -> ImageFont.ImageFont:
        """Load font from available paths."""
        for font_path in cls.FONT_PATHS:
            try:
                font = ImageFont.truetype(font_path, size)
                logger.debug(f"Loaded font: {font_path}")
                return font
            except (OSError, IOError) as e:
                logger.debug(f"Could not load font {font_path}: {e}")
                continue

        # Fallback to default
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            # Older PIL versions don't support size parameter
            return ImageFont.load_default()


class GitManager:
    """Handles git operations for extracting commit data."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def get_recent_commits(self, days: int) -> List[Dict]:
        """Get commits from the last N complete calendar days, excluding current day (midnight to midnight Oslo time)."""
        try:
            # Calculate the start of the earliest day we want (N days ago at midnight Oslo time)
            oslo_tz = zoneinfo.ZoneInfo("Europe/Oslo")
            now_oslo = datetime.now(oslo_tz)

            # Start from N+1 days ago at midnight Oslo time
            start_date_oslo = now_oslo.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days + 1)

            # End at start of today (midnight) to exclude current day completely
            end_date_oslo = now_oslo.replace(hour=0, minute=0, second=0, microsecond=0)

            # Convert to UTC for git
            start_date_utc = start_date_oslo.astimezone(timezone.utc)
            end_date_utc = end_date_oslo.astimezone(timezone.utc)
            since_iso = start_date_utc.isoformat()
            until_iso = end_date_utc.isoformat()

            logger.info(f"Fetching commits from {start_date_oslo.strftime('%Y-%m-%d %H:%M')} to {end_date_oslo.strftime('%Y-%m-%d %H:%M')} Oslo time ({days} complete days, excluding today)")

            cmd = f'git -C "{self.repo_path}" log --since="{since_iso}" --until="{until_iso}" --pretty=format:%H%x00%cI%x00'
            result = subprocess.check_output(cmd, shell=True, text=True).strip()

            return self._parse_commit_output(result)
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {e}")
            return []

    def _parse_commit_output(self, output: str) -> List[Dict]:
        """Parse git log output into commit dictionaries."""
        if not output:
            return []

        commits = []
        parts = output.split("\x00")
        if parts and parts[-1] == "":
            parts = parts[:-1]

        if len(parts) % 2 != 0:
            logger.warning("Unexpected git log output format")
            return []

        for i in range(0, len(parts), 2):
            sha = parts[i].strip()
            date_str = parts[i+1].strip()
            try:
                dt = datetime.fromisoformat(date_str)
                commits.append({"sha": sha, "datetime": dt})
            except ValueError as e:
                logger.warning(f"Could not parse date {date_str}: {e}")
                continue

        return list(reversed(commits))  # oldest to newest

    def copy_images_from_commit(self, commit_sha: str, target_dir: Path, sites: List[str]) -> None:
        """Copy site images from a specific commit using git worktree."""
        tmpdir = Path(tempfile.mkdtemp(prefix="shotscraper_wt_"))
        try:
            # Create detached worktree
            subprocess.run([
                "git", "-C", str(self.repo_path),
                "worktree", "add", "--detach", str(tmpdir), commit_sha
            ], check=True, capture_output=True)

            # Copy files
            for site in sites:
                src = tmpdir / f"{site}.png"
                if src.exists():
                    dst = target_dir / f"{site}.png"
                    shutil.copy2(src, dst)
                    logger.debug(f"Copied {src} -> {dst}")
                else:
                    logger.warning(f"Missing image: {src}")

        except subprocess.CalledProcessError as e:
            logger.error(f"Git worktree operation failed: {e}")
        finally:
            # Cleanup
            subprocess.run([
                "git", "-C", str(self.repo_path),
                "worktree", "remove", "--force", str(tmpdir)
            ], check=False, capture_output=True)
            shutil.rmtree(tmpdir, ignore_errors=True)


class OCRProcessor:
    """Handles OCR text extraction from images."""

    def __init__(self, site_crop_top: Dict[str, int], skip_ocr: bool = False):
        self.site_crop_top = site_crop_top
        self.skip_ocr = skip_ocr

    def extract_text(self, image_path: Path, site: str) -> str:
        """Extract text from image using OCR with site-specific cropping."""
        if self.skip_ocr:
            return ""

        try:
            with Image.open(image_path) as img:
                if site in self.site_crop_top:
                    crop_top = self.site_crop_top[site]
                    w, h = img.size
                    img = img.crop((0, crop_top, w, h))

                text = pytesseract.image_to_string(img, lang="nor+dan")
                return " ".join(text.split())
        except Exception as e:
            logger.error(f"OCR failed for {image_path}: {e}")
            return ""


class FrameProcessor:
    """Processes and combines video frames."""

    def __init__(self, sites: List[str], oslo_tz: zoneinfo.ZoneInfo):
        self.sites = sites
        self.oslo_tz = oslo_tz
        self.font = FontManager.get_font(36)

    def combine_site_images(self, frame_dir: Path, frame_index: int) -> Optional[Image.Image]:
        """Combine site images horizontally for a specific frame."""
        site_images = []

        for site in self.sites:
            path = frame_dir / f"{site}_{frame_index:05d}.png"
            if path.exists():
                try:
                    img = Image.open(path)
                    img.load()  # Force load to detect corruption early
                    site_images.append(img)
                except Exception as e:
                    logger.warning(f"Skipping corrupted image {path}: {e}")
                    continue

        if not site_images:
            return None

        return self._combine_images_horizontally(site_images)

    def _combine_images_horizontally(self, images: List[Image.Image]) -> Image.Image:
        """Combine multiple images side by side."""
        widths, heights = zip(*(img.size for img in images))
        total_width = sum(widths)
        max_height = max(heights)

        combined = Image.new("RGB", (total_width, max_height))
        x_offset = 0

        for img in images:
            combined.paste(img, (x_offset, 0))
            x_offset += img.width

        return combined

    def add_timestamp(self, image: Image.Image, timestamp: str) -> Image.Image:
        """Add timestamp overlay to image."""
        draw = ImageDraw.Draw(image)

        # Calculate text dimensions
        bbox = draw.textbbox((0, 0), timestamp, font=self.font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Draw background rectangle
        padding = 4
        rect_coords = [
            10 - padding, 10 - padding,
            10 + text_width + padding, 10 + text_height + padding
        ]
        draw.rectangle(rect_coords, fill=(0, 0, 0, 128))

        # Draw text
        draw.text((10, 10), timestamp, fill="white", font=self.font)

        return image

    def format_timestamp(self, dt: datetime, frame_index: int) -> str:
        """Format timestamp for display."""
        cet_dt = dt.astimezone(self.oslo_tz)
        return f'Kl. {cet_dt.strftime("%H:%M")}'


class VideoGenerator:
    """Generates time-lapse videos from frames."""

    def __init__(self, config: VideoConfig, base_dir: Path):
        self.config = config
        self.base_dir = base_dir
        self.out_dir = base_dir / "out"
        self.video_dir = self.out_dir / "videos"
        self.metadata_dir = self.out_dir / "metadata"
        self.frames_dir = self.out_dir / "frames_temp"

        self.git_manager = GitManager(base_dir.parent)  # Go up one level to the actual repo root
        self.ocr_processor = OCRProcessor(config.site_crop_top)
        self.oslo_tz = zoneinfo.ZoneInfo("Europe/Oslo")

        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create necessary directories."""
        for directory in [self.out_dir, self.video_dir, self.metadata_dir, self.frames_dir]:
            directory.mkdir(exist_ok=True, parents=True)

    def generate_videos(self, test_frames: Optional[int] = None, skip_ocr: bool = False) -> None:
        """Main entry point for video generation."""
        if skip_ocr:
            self.ocr_processor.skip_ocr = True
            logger.info("OCR skipped for speed testing")

        logger.info(f"Generating videos for last {self.config.archive_days} days...")

        commits = self.git_manager.get_recent_commits(self.config.archive_days)
        if not commits:
            logger.error("No commits found")
            return

        commits_by_day = self._group_commits_by_day(commits)
        logger.info(f"Found {len(commits)} commits across {len(commits_by_day)} days")

        for group in self.config.video_groups:
            self._process_video_group(group, commits_by_day, test_frames)

        if not test_frames:
            self._cleanup_old_files()

        logger.info("All videos generated successfully!")

    def _group_commits_by_day(self, commits: List[Dict]) -> Dict[str, List[Dict]]:
        """Group commits by day in Oslo timezone."""
        commits_by_day = defaultdict(list)

        for commit in commits:
            cet_dt = commit["datetime"].astimezone(self.oslo_tz)
            day_key = cet_dt.strftime("%Y-%m-%d")
            commits_by_day[day_key].append(commit)

        return commits_by_day

    def _process_video_group(self, group: Dict, commits_by_day: Dict, test_frames: Optional[int]) -> None:
        """Process a single video group across all days."""
        group_name = group["name"]
        sites = group["sites"]

        logger.info(f"Processing group '{group_name}' ({', '.join(sites)})")

        for date_str, daily_commits in sorted(commits_by_day.items()):
            if not daily_commits:
                continue

            commits_to_process = daily_commits[:test_frames] if test_frames else daily_commits
            logger.info(f"Processing {date_str}: {len(commits_to_process)} commits")

            self._generate_daily_video(group_name, sites, date_str, commits_to_process, daily_commits, test_frames)

    def _generate_daily_video(self, group_name: str, sites: List[str], date_str: str,
                             commits_to_process: List[Dict], all_commits: List[Dict],
                             test_frames: Optional[int]) -> None:
        """Generate video for a single day."""
        frames_day = self.frames_dir / f"{group_name}_{date_str}"
        frames_day.mkdir(parents=True, exist_ok=True)

        # Extract frames from commits
        self._extract_frames(commits_to_process, frames_day, sites)

        # Generate video
        out_video = self.video_dir / f"{group_name}-{date_str}.mp4"
        self._create_video_from_frames(frames_day, out_video, sites, all_commits)
        logger.info(f"Generated video: {out_video.name}")

        # Generate metadata
        out_json = self.metadata_dir / f"metadata-{group_name}-{date_str}.json"
        self._generate_metadata(frames_day, out_video, out_json, sites, all_commits, test_frames)

    def _extract_frames(self, commits: List[Dict], frames_dir: Path, sites: List[str]) -> None:
        """Extract and rename frames from git commits."""
        for i, commit in enumerate(commits):
            logger.debug(f"Processing frame {i}: commit {commit['sha']}")

            # Copy images from commit
            self.git_manager.copy_images_from_commit(commit['sha'], frames_dir, sites)

            # Rename to frame sequence
            for site in sites:
                src = frames_dir / f"{site}.png"
                if src.exists():
                    dst = frames_dir / f"{site}_{i:05d}.png"
                    src.rename(dst)
                    logger.debug(f"Renamed {src.name} -> {dst.name}")

    def _create_video_from_frames(self, frames_dir: Path, output_path: Path,
                                 sites: List[str], commits: List[Dict]) -> None:
        """Create video from frame sequence."""
        frame_processor = FrameProcessor(sites, self.oslo_tz)

        # Get frame indices
        frame_indices = self._get_frame_indices(frames_dir, sites[0])
        if not frame_indices:
            logger.error(f"No frames found for {sites[0]}")
            return

        # Process frames and calculate durations
        combined_frames = []
        frame_durations = []

        for idx in frame_indices:
            # Combine site images
            combined_img = frame_processor.combine_site_images(frames_dir, idx)
            if not combined_img:
                logger.warning(f"No valid images for frame {idx}")
                continue

            # Add timestamp
            if idx < len(commits):
                timestamp = frame_processor.format_timestamp(commits[idx]["datetime"], idx)
            else:
                timestamp = f"Frame {idx:05d}"

            combined_img = frame_processor.add_timestamp(combined_img, timestamp)

            # Save combined frame
            combined_path = frames_dir / f"combined_{idx:05d}.png"
            combined_img.save(combined_path)
            combined_frames.append(combined_path)

            # Calculate duration
            duration = self._calculate_frame_duration(commits, idx)
            frame_durations.append(duration)

        # Generate video with FFmpeg
        self._generate_video_with_ffmpeg(combined_frames, frame_durations, output_path, frames_dir)

    def _get_frame_indices(self, frames_dir: Path, reference_site: str) -> List[int]:
        """Get sorted list of frame indices."""
        return sorted({
            int(f.name.split("_")[-1].split(".")[0])
            for f in frames_dir.glob(f"{reference_site}_*.png")
        })

    def _calculate_frame_duration(self, commits: List[Dict], frame_index: int) -> float:
        """Calculate how long a frame should be displayed."""
        if frame_index < len(commits) - 1:
            delta_sec = (commits[frame_index + 1]["datetime"] - commits[frame_index]["datetime"]).total_seconds()
        else:
            delta_sec = 5 * 60  # Default 5 minutes for last frame

        return max(delta_sec / self.config.speedup_factor, 0.01)

    def _generate_video_with_ffmpeg(self, frames: List[Path], durations: List[float],
                                   output_path: Path, frames_dir: Path) -> None:
        """Generate video using FFmpeg."""
        concat_file = frames_dir / "frames.txt"

        with open(concat_file, "w") as f:
            for frame_path, duration in zip(frames, durations):
                f.write(f"file '{frame_path}'\n")
                f.write(f"duration {duration}\n")
            # Repeat last frame
            if frames:
                f.write(f"file '{frames[-1]}'\n")

        cmd = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(concat_file),
            '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            str(output_path), '-loglevel', 'error'
        ]

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg failed: {e}")
            raise

    def _generate_metadata(self, frames_dir: Path, video_path: Path,
                          metadata_path: Path, sites: List[str], commits: List[Dict],
                          max_frames: Optional[int]) -> None:
        """Generate metadata JSON for the video."""
        frames = sorted(frames_dir.glob("combined_*.png"))
        if max_frames:
            frames = frames[:max_frames]

        metadata = []
        cumulative_time = 0.0

        for i, frame in enumerate(frames):
            frame_data = {
                "frame_index": i,
                "video_time": cumulative_time,
                "video_name": video_path.name,
            }

            # Add burnt-in timestamp (the actual Oslo time when screenshot was taken)
            if commits and i < len(commits):
                commit_dt = commits[i]["datetime"]
                oslo_time = commit_dt.astimezone(self.oslo_tz)
                frame_data["burnt_in_time"] = oslo_time.strftime("%H:%M")

            # Calculate actual frame duration based on commit time gaps
            if commits and i < len(commits):
                if i < len(commits) - 1:
                    delta_sec = (commits[i + 1]["datetime"] - commits[i]["datetime"]).total_seconds()
                else:
                    delta_sec = 5 * 60  # default 5 minutes for last frame
                frame_duration = max(delta_sec / self.config.speedup_factor, 0.01)
                cumulative_time += frame_duration
            else:
                # Fallback to 30fps if no commit data
                cumulative_time += 0.033

            # Add OCR data for each site
            for site in sites:
                site_frame = frames_dir / f"{site}_{i:05d}.png"
                if site_frame.exists():
                    frame_data[site] = self.ocr_processor.extract_text(site_frame, site)

            metadata.append(frame_data)

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"Generated metadata: {metadata_path.name}")

    def _cleanup_old_files(self) -> None:
        """Remove old video and metadata files."""
        for group in self.config.video_groups:
            group_name = group["name"]

            # Cleanup videos
            video_files = sorted(self.video_dir.glob(f"{group_name}-*.mp4"))
            for old_file in video_files[:-self.config.archive_days]:
                logger.info(f"Removing old video: {old_file.name}")
                old_file.unlink()

            # Cleanup metadata
            metadata_files = sorted(self.metadata_dir.glob(f"metadata-{group_name}-*.json"))
            for old_file in metadata_files[:-self.config.archive_days]:
                logger.info(f"Removing old metadata: {old_file.name}")
                old_file.unlink()

        # Cleanup temporary frame directories
        if self.frames_dir.exists():
            logger.info("Cleaning up temporary frame directories")
            shutil.rmtree(self.frames_dir, ignore_errors=True)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate news timelapse videos.")
    parser.add_argument("--test-frames", type=int, help="Test mode: only generate N frames per day")
    parser.add_argument("--skip-ocr", action="store_true", help="Skip OCR text extraction for faster testing")
    args = parser.parse_args()

    # Setup paths
    base_dir = Path(__file__).resolve().parent.parent
    config_file = base_dir / "config.yaml"

    # Load configuration
    config = VideoConfig.from_yaml(config_file)

    # Create and run video generator
    generator = VideoGenerator(config, base_dir)
    generator.generate_videos(args.test_frames, args.skip_ocr)


if __name__ == "__main__":
    main()