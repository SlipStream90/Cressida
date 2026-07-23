"""CRESSIDA learning layer — the closed self-improvement loop.

Inspired by Nous Research's Hermes agent: agents accumulate reusable experience,
that experience is curated and consolidated, and it is fed back into every future
prompt so behaviour improves over missions instead of resetting each time.

Components
----------
- PlaybookStore    : per-agent evolving "playbook" of learned heuristics. Ranked,
                     deduplicated, and bounded so it stays token-cheap. Injected
                     into every prompt by the ContextBuilder.
- ReflectionEngine : runs after a mission, distils what worked / what didn't from
                     reward signals and task outcomes into playbook entries.
- SkillSynthesizer : autonomous skill creation — turns a novel, successful task
                     pattern into a reusable procedure note under knowledge/skills/.
- Curator          : the "periodic nudge" — consolidates and decays playbooks so
                     knowledge does not bloat or go stale.
"""

from .playbook import PlaybookStore, PlaybookEntry
from .reflection import ReflectionEngine, Insight
from .skills import SkillSynthesizer
from .curator import Curator

__all__ = [
    "PlaybookStore",
    "PlaybookEntry",
    "ReflectionEngine",
    "Insight",
    "SkillSynthesizer",
    "Curator",
]
