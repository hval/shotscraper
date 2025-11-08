# 📰 Frontskudd - Norwegian News Timelapse

Frontskudd creates time-lapse videos showing how Norwegian news websites change throughout the day. It processes screenshots captured by the shotscraper workflow and generates interactive video timelines.

## Features

- **Time-lapse videos** from website screenshots stored in git history
- **OCR text extraction** for searchable content
- **Interactive web interface** with clickable search results
- **Norwegian localization** with proper timezone handling
- **Configurable video groups** and processing settings

## How it Works

1. **Screenshots** are captured every 5 minutes by the shotscraper workflow
2. **Nightly processing** (2:00 AM Oslo time) generates videos from the last 3 complete days
3. **OCR extraction** makes all text in screenshots searchable
4. **Web interface** is automatically deployed to GitHub Pages

## Configuration

Edit `config.yaml` to customize:

```yaml
archive_days: 3                    # Number of complete days to include
speedup_factor: 600               # Video acceleration (600x = 10min → 1sec)
description: "Your description"   # Web interface description

videos:
  - name: nettavisen_vg_db        # Technical name
    title: "Nettavisen, VG og Dagbladet"  # Display title
    sites: [nettavisen, vg, db]   # Sites to include

site_crop_top:
  nettavisen: 130                 # Pixels to crop from top
  vg: 100
  db: 130
```

## Local Development

```bash
# Generate videos (from frontskudd directory)
python scripts/generate_videos.py

# Generate HTML interface
python scripts/generate_html.py

# Test with limited frames
python scripts/generate_videos.py --test-frames 10

# Skip OCR for faster testing
python scripts/generate_videos.py --skip-ocr
```

## Dependencies

- Python 3.11+
- FFmpeg
- Tesseract OCR
- PyYAML, Pillow, pytesseract (see requirements.txt)

## GitHub Actions

The nightly workflow:
1. Processes git history to extract screenshot commits
2. Groups screenshots by date and site
3. Generates MP4 videos with burnt-in timestamps
4. Extracts searchable text via OCR
5. Creates interactive HTML interface
6. Deploys to GitHub Pages

## Output Structure

```
out/
├── index.html                    # Interactive web interface
├── videos/                       # Generated MP4 files
│   ├── nettavisen_vg_db-2025-11-07.mp4
│   └── ...
└── metadata/                     # OCR text and timestamps
    ├── metadata-nettavisen_vg_db-2025-11-07.json
    └── ...
```

## Web Interface Features

- **Day selector dropdown** with Norwegian day names
- **Video search** with clickable results that jump to specific timestamps
- **Responsive design** with dark mode support
- **Real-time timestamps** showing both actual time and video position

---

*Automatically generated with ❤️ by GitHub Actions*