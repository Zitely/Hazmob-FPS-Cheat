"""Pure targeting math; no screen capture or mouse input."""
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float


def choose_target(detections, center, radius, confidence, height_fraction=0.15):
    candidates = []
    for d in detections:
        if d.confidence < confidence or d.x2 <= d.x1 or d.y2 <= d.y1:
            continue
        point = ((d.x1 + d.x2) / 2, d.y1 + (d.y2 - d.y1) * height_fraction)
        distance = math.hypot(point[0] - center[0], point[1] - center[1])
        if distance <= radius:
            candidates.append((distance, point, d))
    return min(candidates, key=lambda item: item[0]) if candidates else None


def movement(point, center, gain, max_step=12, deadzone=2):
    dx, dy = point[0] - center[0], point[1] - center[1]
    distance = math.hypot(dx, dy)
    if distance <= deadzone:
        return (0, 0)
    dx, dy = dx * gain, dy * gain
    length = math.hypot(dx, dy)
    if length > max_step:
        dx, dy = dx * max_step / length, dy * max_step / length
    return round(dx), round(dy)


def may_move(armed, enabled, held, same_window, age, stop):
    return bool(armed and enabled and held and same_window and not stop and 0 <= age <= 0.20)


def head_point(keypoints, box, threshold=0.6):
    """Confidence-weighted visible nose/eye/ear point; no body-box fallback."""
    valid = []
    for row in list(keypoints)[:5]:
        if len(row) < 3:
            continue
        x, y, confidence = map(float, row[:3])
        if not all(math.isfinite(v) for v in (x, y, confidence)):
            continue
        if confidence < threshold or (x == 0 and y == 0):
            continue
        if not (box.x1 <= x <= box.x2 and box.y1 <= y <= box.y1 + (box.y2-box.y1)*0.5):
            continue
        valid.append((x, y, confidence))
    if len(valid) < 2:
        return None
    weight = sum(v[2] for v in valid)
    return (sum(v[0]*v[2] for v in valid)/weight,
            sum(v[1]*v[2] for v in valid)/weight)


def choose_head(candidates, center, radius):
    eligible = []
    for point, box in candidates:
        if point is None:
            continue
        distance = math.hypot(point[0]-center[0], point[1]-center[1])
        if distance <= radius:
            eligible.append((distance, point, box))
    return min(eligible, key=lambda item: item[0]) if eligible else None
