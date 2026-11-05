# Hazmob Snap — experimental head-keypoint aimbot

## Version 1.3.0
- Aimbot has one on/off toggle. There are no sensitivity, gain, confidence, or targeting sliders.
- Targets must match across three frames before movement begins. A persistent lock resists switching to a different player just because that player becomes closer to the crosshair.
- Missing and ambiguous targets produce no aiming movement. Reacquisition has a short cooldown.
- Bounded corrections replace the previous 240-count jumps. Per-axis damping reduces response when the crosshair overshoots. A four-pixel settling zone avoids constant jitter.
- Player ESP is now a transparent, click-through overlay on the game monitor, with separate skeleton, head marker, target circle and crosshair toggles.
- The overlay excludes itself from screen capture so its drawings are not fed back into the detector. If Windows cannot exclude it, overlay display is disabled.
- The version appears in the bottom-right corner of the app and overlay.

## Run
Extract the latest Windows release and run Start.cmd. The model loads automatically. Turn on Aimbot or Player ESP and return to Hazmob running full-screen in Chrome. F8 pauses/resumes all features; F9 exits. There is no requirement to hold RMB for aiming. Firing remains manual.

On first setup the launcher asks before installing dependencies (several hundred MB); the pose model is downloaded when first loaded. Model weights and dependencies are reused on updates. Close old copies before starting a new version.

## Feature toggles
- Aimbot: track a confirmed visible head with fixed internal defaults.
- Player ESP: boxes around visible detected players across the captured monitor.
- Skeleton: show detected limb keypoints when Player ESP is enabled.
- Head markers: mark head detections when Player ESP is enabled.
- Target circle: show the aiming area.
- Crosshair: center-screen crosshair.
- Recoil compensation: fixed downward input while holding both mouse buttons, used only when the head controller is not already aiming. This does not remove the game's recoil.

## Limits
The model is a general human pose detector, not trained specifically on Hazmob. It cannot reliably identify teams, may miss stylized or distant characters, and does not read game memory. ESP shows visible detections, not players behind walls. Memory-based wallhacks, firing through walls, no spread, health and ammo changes are not implemented. A visual overlay cannot override game/server collision or hit validation.

Use full-screen mode so the monitor center matches the crosshair. Aiming and overlays reject stale frames. Input still depends on the game's acceptance of ordinary Windows mouse movement. Fixed defaults and overshoot damping address the observed code issues but do not guarantee a one-frame headshot or perfect calibration for every game sensitivity. Full-monitor detection improves overlay coverage but can reduce small-head detection compared with a center crop.

## Validation
24 portable tests cover targeting, lock retention, loss/ambiguity, simulated high-sensitivity settling, updater integrity and release selection. Windows UI checks verify that there are no numeric controls, the version label exists, overlay drawing and cleanup work, and Windows accepts click-through/no-activation/capture-exclusion settings. The UI was visually inspected. No live match accuracy or wall penetration was verified.

## References
- Model: https://docs.ultralytics.com/models/yolo11/
- Pose keypoints: https://docs.ultralytics.com/tasks/pose/
- Overlay capture exclusion: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity
Ultralytics packages and model weights remain subject to their upstream licensing.

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
