from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Character, Episode, Event, Relationship


def normalize_name(name: str) -> str:
    value = name.strip().casefold()
    value = re.sub(r"\s+", " ", value)
    return value


def _find_character(characters: Iterable[Character], name: str) -> Character | None:
    normalized = normalize_name(name)
    for character in characters:
        if normalize_name(character.name) == normalized or normalized in {normalize_name(a) for a in (character.aliases or [])}:
            return character
    return None


def persist_analysis(db: Session, project_id: str, episode: Episode, result: dict) -> dict:
    characters = db.scalars(select(Character).where(Character.project_id == project_id)).all()
    created_characters = 0
    merged_characters = 0

    for item in result.get("characters", []):
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        character = _find_character(characters, name)
        if character is None:
            character = Character(project_id=project_id, name=name, role=item.get("role"), aliases=[])
            db.add(character)
            characters.append(character)
            created_characters += 1
        else:
            merged_characters += 1
            role = item.get("role")
            if role and not character.role:
                character.role = role
            if name.casefold() != character.name.casefold() and name not in (character.aliases or []):
                character.aliases = [*(character.aliases or []), name]

    db.flush()
    by_name = {normalize_name(c.name): c for c in characters}
    for character in characters:
        for alias in character.aliases or []:
            by_name[normalize_name(alias)] = character

    created_events = 0
    for item in result.get("events", []):
        title = str(item.get("event", "")).strip()
        if not title:
            continue
        db.add(Event(project_id=project_id, episode_id=episode.id, title=title, evidence=item.get("evidence"), metadata={"characters": item.get("characters", [])}))
        created_events += 1

    created_relationships = 0
    for item in result.get("relationships", []):
        source = by_name.get(normalize_name(str(item.get("from", ""))))
        target = by_name.get(normalize_name(str(item.get("to", ""))))
        if not source or not target:
            continue
        db.add(Relationship(project_id=project_id, from_character_id=source.id, to_character_id=target.id, relation=str(item.get("relation", "")).strip(), evidence=item.get("evidence")))
        created_relationships += 1

    episode.analysis = result
    db.flush()
    return {"characters_created": created_characters, "characters_matched": merged_characters, "events_created": created_events, "relationships_created": created_relationships}


def build_timeline(db: Session, project_id: str) -> list[dict]:
    episodes = db.scalars(select(Episode).where(Episode.project_id == project_id).order_by(Episode.created_at.asc())).all()
    events = db.scalars(select(Event).where(Event.project_id == project_id).order_by(Event.created_at.asc())).all()
    by_episode: dict[str, list[dict]] = {episode.id: [] for episode in episodes}
    for event in events:
        by_episode.setdefault(event.episode_id, []).append({"id": event.id, "title": event.title, "evidence": event.evidence, "characters": (event.metadata or {}).get("characters", [])})
    return [{"episode_id": episode.id, "episode_title": episode.title, "created_at": episode.created_at, "events": by_episode.get(episode.id, [])} for episode in episodes]
