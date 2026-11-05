# Hazmob Snap — experimental head-keypoint aimbot

## What's different
- Automatic head snapping after you arm it with F8; no RMB requirement by default.
- Uses YOLO11n-pose nose, eye and ear keypoints. At least two confident keypoints must lie in the upper portion of a detected person's box.
- Targets the nearest eligible head point inside the selection radius.
- Does not estimate head position from a plain body box when head keypoints are unavailable.
- Removed the previous low-gain smoothing and 12-count movement limit. Default snap gain is 1.0, with a maximum 240 relative mouse counts per update.
- F8 pauses/resumes. F9 exits. Focus loss stops input.

## Launch
Extract all files and run Start.cmd. First setup asks before downloading the CPU AI runtime and dependencies (several hundred MB). It requires Python 3.10–3.13 with tkinter; the launcher can use Codex's bundled Python. Otherwise install 64-bit Python 3.12 from https://www.python.org/downloads/windows/.

For an existing installation, extract the full release ZIP over the application files to adopt the GitHub updater; keep your .venv and model files. Close the old version first. Do not run both simultaneously.

Click Load detector. First load downloads yolo11n-pose.pt. Open Hazmob full-screen using the game's fullscreen button in Chrome. Press F8 to activate automatic snapping. Snap aiming is enabled by default but the application starts paused. Shots are still manual. Enable Require RMB if you want hold-to-aim behavior. Uncheck Snap aiming to inspect detections without moving the mouse.

## Calibration
Screen pixels and mouse-input counts are not the same unit. A gain of 1.0 is a starting point, not a calibrated one-frame headshot guarantee. Reduce Snap sensitivity if it overshoots; increase it if it undershoots. Tune while using one consistent game sensitivity. The next detection corrects the remaining error, so snapping may take several frames. The target radius controls how far from the center an eligible head can be selected.

Head keypoint confidence controls how certain facial/ear landmarks must be. Low confidence can create false targets; high confidence may reject small or stylized heads. The preview marks head candidates in purple and the selected point in orange.

## Limits
This is a general human pose model, NOT a Hazmob-trained detector. Actual enemy-head detection and game input compatibility are unverified. It may target teammates and cannot see through walls. Estimated facial landmarks are not the game's exact head hitbox. No confident head means no snap target. It does not change health/ammo, remove spread, automatically fire, or bypass the game's input handling. Downward compensation is an optional fixed mouse pull while LMB is held, not actual recoil removal; it defaults to zero.

The capture region is centered on the monitor containing the active Chrome/Hazmob window. Use true game fullscreen. Mouse movement is suspended if inference takes more than 200 ms. The 640-pixel pose inference can be slower than the previous model, especially on older CPUs. Captures and inference are local; only dependencies and model weights are downloaded.

## Checked
Six targeted tests cover head confidence, missing/invalid keypoints, target selection, snap movement limits, focus, latency, and stopping. Hidden UI construction and Windows INPUT layout checks passed. No live model inference, screen capture, or mouse input was performed during development. No verified in-game accuracy is claimed.

## References
- Model: https://docs.ultralytics.com/models/yolo11/
- Head landmark indices: https://docs.ultralytics.com/tasks/pose/
- Windows relative mouse input: https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-mouseinput
Ultralytics packages and model weights are subject to their upstream AGPL-3.0 or enterprise licensing. Review those terms before redistribution.

## Automatic updates from GitHub

Download **HazmobSnap-Windows.zip** from [the latest release](https://github.com/Zitely/Hazmob-FPS-Cheat/releases/latest), extract it, and use Start.cmd.

Every launch checks this public feed:
https://github.com/Zitely/Hazmob-FPS-Cheat/releases/latest/download/manifest.json

Newer app versions are downloaded, checksum-checked, syntax-checked, and activated as complete releases. Missing or invalid updates leave the installed version available. Restart to install a newly published release. Model weights and the Python environment remain in the app folder. If requirements change, the launcher installs the new requirements before starting.

This checks integrity against the configured HTTPS feed, not an independent publisher signature. Releases contain app.py, targeting.py, requirements.txt and README.md. The stable launcher/updater bootstrap is included in the full installer ZIP; changes to that bootstrap require replacing those files once.

## Publish a new version

1. Change the source and increment version.txt (for example, 1.2.0 to 1.2.1).
2. Commit to main. GitHub Actions tests and builds the release.
3. The workflow publishes the app ZIP, updater manifest, and Windows installer as a GitHub Release. Installed copies pick up the new app version next launch.

The workflow uses the repository's built-in GitHub token with contents:write, without a personal token. It publishes only files explicitly listed in tools/build_release.py; model weights, environments, installed package lists, and local runtime data are excluded.

Run portable tests with `python -m unittest discover -s tests`. Build packages locally with `python tools/build_release.py`.
