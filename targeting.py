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


def box_iou(a, b):
    left, top = max(a.x1, b.x1), max(a.y1, b.y1)
    right, bottom = min(a.x2, b.x2), min(a.y2, b.y2)
    intersection = max(0, right-left) * max(0, bottom-top)
    union = (a.x2-a.x1)*(a.y2-a.y1) + (b.x2-b.x1)*(b.y2-b.y1) - intersection
    return intersection / union if union > 0 else 0


class StableLock:
    """Confirm a target across frames; retain it instead of choosing nearest each frame."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.box = None
        self.point = None
        self.confirmations = 0
        self.last_seen = 0.0
        self.cooldown = 0.0
        self.generation = 0

    def update(self, candidates, center, radius, now):
        valid = [(p,b) for p,b in candidates if p is not None
                 and b.x2-b.x1 >= 12 and b.y2-b.y1 >= 28
                 and math.hypot(p[0]-center[0],p[1]-center[1]) <= radius]
        if self.box is not None:
            matches = []
            for point, box in valid:
                overlap = box_iou(self.box, box)
                separation = math.hypot(point[0]-self.point[0],point[1]-self.point[1])
                if overlap >= .18 and separation <= max(55, (self.box.x2-self.box.x1)*.8):
                    matches.append((overlap - separation/1000, point, box))
            matches.sort(key=lambda item:item[0], reverse=True)
            ambiguous = len(matches)>1 and matches[0][0]-matches[1][0] < .08
            if matches and not ambiguous:
                _, self.point, self.box = matches[0]
                self.confirmations += 1
                self.last_seen = now
                if self.confirmations >= 3:
                    return (math.dist(self.point,center), self.point, self.box)
                return None
            # Never act on a stale remembered position, or switch immediately after loss.
            if now-self.last_seen >= .18:
                self.box, self.point, self.confirmations = None, None, 0
                self.cooldown = now+.25
            return None
        if now < self.cooldown:
            return None
        choice = choose_head(valid, center, radius)
        if choice:
            _, self.point, self.box = choice
            self.last_seen = now
            self.confirmations = 1
            self.generation += 1
        return None


class SettlingController:
    """Bounded closed-loop movement with per-axis overshoot damping."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.gains = [.20, .20]
        self.previous = [None, None]
        self.last_time = None

    def step(self, point, center, now):
        if self.last_time is not None and now-self.last_time < .025:
            return (0,0)
        self.last_time = now
        error = [point[0]-center[0], point[1]-center[1]]
        output = []
        for axis, value in enumerate(error):
            old = self.previous[axis]
            if old is not None and value*old < 0 and abs(value)>4 and abs(old)>4:
                self.gains[axis] = max(.025, self.gains[axis]*.5)
            self.previous[axis] = value
            output.append(0 if abs(value)<=4 else value*self.gains[axis])
        length = math.hypot(*output)
        # Fast approach, small corrections near the head; never the old 240-count jump.
        limit = 24 if math.hypot(*error)>70 else 8
        if length>limit:
            output = [v*limit/length for v in output]
        return tuple(round(v) for v in output)
