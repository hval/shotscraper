# 📸 Frontpage Screenshot Archive + 📰 Timelapse Videos

This repository combines automated screenshot capture with time-lapse video generation for Norwegian news websites.

## Two-Part System

### 🔄 Screenshot Capture (Every 5 minutes)
- Uses [shot-scraper](https://github.com/simonw/shot-scraper) to capture news front pages
- Monitors: Nettavisen, VG, Dagbladet, BA, DT, BT
- Stores screenshots in git history
- Runs via GitHub Actions every 5 minutes

### 🎬 Frontskudd Timelapse (Nightly at 2 AM)
- Processes screenshot history into time-lapse videos
- Extracts searchable text via OCR
- Generates interactive web interface
- Deploys to GitHub Pages

## Quick Start

### For Screenshots
Screenshots are captured automatically. Current sites in `shots.yml`:
- [Nettavisen](https://www.nettavisen.no)
- [VG](https://www.vg.no/)
- [Dagbladet](https://www.dagbladet.no/)
- [BA](https://www.ba.no/)
- [DT](https://www.dt.no/)
- [BT](https://www.bt.no/)
- [BT.dk](https://www.bt.dk/)
- [Ekstrabladet](https://www.ekstrabladet.dk/)

### For Timelapse Videos
1. **View the interface**: Visit the deployed GitHub Pages site
2. **Configure**: Edit `frontskudd/config.yaml`
3. **Manual trigger**: Run the "Frontskudd" GitHub Action

## Repository Structure

```
├── shots.yml                     # Screenshot configuration
├── requirements.txt              # Python dependencies
├── .github/workflows/
│   ├── shots.yml                 # 5-minute screenshot capture
│   └── frontskudd.yml           # Nightly video generation
├── frontskudd/                   # Timelapse video system
│   ├── config.yaml              # Frontskudd configuration
│   ├── scripts/
│   │   ├── generate_videos.py
│   │   └── generate_html.py
│   └── out/                     # Generated videos & web interface
└── *.png                        # Latest screenshots
```

## Configuration

### Screenshots (`shots.yml`)
```yaml
- url: https://www.nettavisen.no
  output: nettavisen.png
  height: 800
  width: 500
  wait: 5000
```

### Timelapse (`frontskudd/config.yaml`)
```yaml
archive_days: 3                    # Days to include in videos
speedup_factor: 600               # 600x speed (10min → 1sec)
description: "News timeline"      # Web interface description

videos:
  - name: nettavisen_vg_db
    title: "Nettavisen, VG og Dagbladet"
    sites: [nettavisen, vg, db]
```

## GitHub Actions

### Screenshot Workflow
- **Schedule**: Every 5 minutes
- **Action**: Capture screenshots, commit to git
- **Trigger**: Automatic + manual

### Frontskudd Workflow
- **Schedule**: 2:00 AM Oslo time daily
- **Action**: Generate videos, deploy web interface
- **Trigger**: Automatic + manual
- **Output**: GitHub Pages deployment

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Generate videos (run from frontskudd/ directory)
cd frontskudd
python scripts/generate_videos.py

# Generate web interface
python scripts/generate_html.py

# Test with limited frames
python scripts/generate_videos.py --test-frames 5 --skip-ocr
```

## System Requirements

- **Python 3.11+**
- **FFmpeg** (video processing)
- **Tesseract OCR** (text extraction)
- **Playwright** (screenshot capture)

## Features

### Screenshot Features
- ✅ Automated 5-minute capture
- ✅ Cookie banner removal
- ✅ Git-based version history
- ✅ Multiple Norwegian news sites

### Timelapse Features
- ✅ Time-lapse video generation
- ✅ OCR text extraction & search
- ✅ Interactive web interface
- ✅ Norwegian timezone handling
- ✅ Responsive design with dark mode
- ✅ Clickable search results with timestamp navigation

## Deployment

The system automatically deploys to GitHub Pages at:
`https://hval.github.io/shotscraper`

## Contributing

1. Screenshots: Edit `shots.yml` to add/modify sites
2. Timelapse: Edit `frontskudd/config.yaml` for video settings
3. Code: Both workflows support manual triggers for testing

---

**Live Demo**: [View the latest timelapse →](https://hval.github.io/shotscraper)

*Built with shot-scraper, Python, FFmpeg, and ❤️*
