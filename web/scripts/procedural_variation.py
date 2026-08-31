"""Seeded geometry and auditable variation identities, independent of rendering.

A fingerprint describes actual generated parameters, never merely a new seed or
title. It is not a perceptual-similarity score or a promise of infinite content.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import random


def scoped_random(seed: int, scope: str) -> random.Random:
    digest = hashlib.sha256(f"clipmaker-variation-v1:{scope}:{int(seed)}".encode()).digest()
    return random.Random(int.from_bytes(digest, "big"))


def variation_manifest(game: str, parameters: dict) -> dict:
    # JSON also snapshots lists so later simulation cannot mutate the manifest.
    encoded = json.dumps(parameters, sort_keys=True, separators=(",", ":"), allow_nan=False)
    fingerprint = hashlib.sha256(f"{game}:v1:{encoded}".encode()).hexdigest()
    return {
        "variation_version": 1,
        "variation_fingerprint": fingerprint,
        "variation_parameters": json.loads(encoded),
    }


@dataclass(frozen=True)
class OrganicContour:
    lobes: int
    secondary_lobes: int
    ripple_lobes: int
    amplitude: float
    secondary_amplitude: float
    ripple_amplitude: float
    drift: float

    def terms(self, angle: float, phase: float, layer: int, time: float):
        return (
            (self.amplitude, self.lobes, angle * self.lobes + phase + layer * .012, 0.0),
            (self.secondary_amplitude, self.secondary_lobes, angle * self.secondary_lobes - phase * .7, 0.0),
            (self.ripple_amplitude, self.ripple_lobes,
             angle * self.ripple_lobes + phase * 1.8 + time * self.drift, self.drift),
        )

    def sample(self, angle: float, phase: float, layer: int = 0, time: float = 0.0):
        """Radius factor, angular derivative and radial velocity share one curve."""
        terms = self.terms(angle, phase, layer, time)
        return (
            1.0 + sum(a * math.sin(p) for a, _n, p, _d in terms),
            sum(a * n * math.cos(p) for a, n, p, _d in terms),
            sum(a * d * math.cos(p) for a, _n, p, d in terms),
        )


def organic_contour_for_seed(seed: int) -> OrganicContour:
    rng = scoped_random(seed, "organic-contour")
    lobes = rng.choice((5, 6, 7, 8, 9))
    secondary_lobes = rng.choice((2, 3, 4))
    # Bound BOTH displacement and slope by the former seven-lobe contour.
    # Narrow spikes cannot appear merely because the frequency increased.
    return OrganicContour(
        lobes=lobes,
        secondary_lobes=secondary_lobes,
        ripple_lobes=rng.choice((11, 12, 13)),
        amplitude=rng.uniform(.064, .084) * min(1.0, 7 / lobes),
        secondary_amplitude=rng.uniform(.018, .032) * min(1.0, 3 / secondary_lobes),
        ripple_amplitude=rng.uniform(.007, .013),
        drift=rng.uniform(.20, .30),
    )


def game_variation_manifest(game_id: str, game) -> dict:
    """Call immediately after world creation, before advancing the simulation."""
    if game_id == "ball-escape":
        parameters = {"radii": game.radii, "gap_widths": game.gap_widths,
                      "gaps": game.base_gaps, "rotations": game.rotations,
                      "launch_velocity": game.velocity}
    elif game_id == "shape-tunnel":
        parameters = {"contour": asdict(game.contour), "phase": game.shape_phase,
                      "launch_velocity": game.velocity, "gravity": game.gravity,
                      "restitution": game.restitution, "layers": game.total}
    elif game_id == "laser-dodge":
        parameters = {"lasers": [{k: v for k, v in laser.items() if k != "hue"}
                                 for laser in game.lasers],
                      "runner_velocity": game.initial_velocity,
                      "max_speed": game.max_speed, "max_acceleration": game.max_acceleration}
    elif game_id == "boss-battle":
        parameters = {"player": game.player_body, "boss": game.boss_body,
                      "player_weapon": game.player_mace, "boss_weapon": game.boss_mace,
                      "motors": [game.player_motor_speed, game.boss_motor_speed,
                                 game.player_motor_phase, game.boss_motor_phase],
                      "boss_hp": game.boss_max}
    else:
        raise ValueError(f"Unknown procedural game: {game_id}")
    parameters.update({"canvas": [game.width, game.height], "duration": game.duration})
    return variation_manifest(game_id, parameters)
