import string
import random
import json
import logging
from datetime import datetime, timedelta
from typing import List, Tuple
import pytz
from db import db
from sqlalchemy import func

logger = logging.getLogger(__name__)


class Meeting(db.Model):
    __tablename__ = 'meetings'
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(16), unique=True, nullable=False, index=True)
    organizer_name = db.Column(db.String(255), nullable=False)
    organizer_email = db.Column(db.String(255), nullable=False)
    meeting_title = db.Column(db.String(255), nullable=False)
    time_slots_json = db.Column(db.Text, nullable=False)  # JSON-encoded list of strings
    timezone = db.Column(db.String(64), default='US/Mountain')
    notification_preferences_json = db.Column(db.Text, default='{}')
    expected_participants = db.Column(db.Integer, default=5)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    responses = db.relationship('Response', backref='meeting', cascade='all, delete-orphan', lazy=True)

    @property
    def time_slots(self) -> List[str]:
        """Return display strings for slots (backward-compatible).

        Internally we may store either:
        - A list of display strings (legacy)
        - A list of objects: {display, start_utc, end_utc, tz}
        """
        try:
            raw = json.loads(self.time_slots_json or '[]')
            if not isinstance(raw, list):
                return []
            display_list: List[str] = []
            for item in raw:
                if isinstance(item, dict) and 'display' in item:
                    display_list.append(item['display'])
                elif isinstance(item, str):
                    display_list.append(item)
            return display_list
        except Exception:
            return []

    @time_slots.setter
    def time_slots(self, value: List[str]):
        # Setter remains simple; callers can still set strings if desired
        self.time_slots_json = json.dumps(value or [])

    @property
    def slots_meta(self) -> List[dict]:
        """Return canonical slots with metadata if available.

        Each item: {display, start_utc, end_utc, tz}
        """
        try:
            raw = json.loads(self.time_slots_json or '[]')
            if not isinstance(raw, list):
                return []
            meta = []
            for item in raw:
                if isinstance(item, dict) and all(k in item for k in ['display', 'start_utc', 'end_utc', 'tz']):
                    meta.append(item)
            return meta
        except Exception:
            return []

    @property
    def notification_preferences(self) -> dict:
        try:
            return json.loads(self.notification_preferences_json or '{}')
        except Exception:
            return {}

    @notification_preferences.setter
    def notification_preferences(self, value: dict):
        self.notification_preferences_json = json.dumps(value or {})


class Response(db.Model):
    __tablename__ = 'responses'
    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey('meetings.id', ondelete='CASCADE'), nullable=False, index=True)
    respondent_name = db.Column(db.String(255), nullable=False)
    available_slots_json = db.Column(db.Text, nullable=False)  # JSON-encoded list of indices
    no_availability = db.Column(db.Boolean, default=False)
    responded_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def available_slots(self) -> List[int]:
        try:
            return json.loads(self.available_slots_json or '[]')
        except Exception:
            return []

    @available_slots.setter
    def available_slots(self, value: List[int]):
        self.available_slots_json = json.dumps(value or [])


class MeetingStore:
    """SQLAlchemy-backed storage for meetings and responses"""

    def __init__(self):
        pass

    def generate_token(self) -> str:
        """Generate a unique 6-character token"""
        while True:
            token = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
            exists = db.session.query(Meeting.id).filter_by(token=token).first()
            if not exists:
                return token

    def create_meeting(self, organizer_name, organizer_email, meeting_title, time_slots, timezone='US/Mountain', notification_preferences=None, expected_participants=5) -> str:
        """Create a new meeting and return its token"""
        token = self.generate_token()
        meeting = Meeting(
            token=token,
            organizer_name=organizer_name,
            organizer_email=organizer_email,
            meeting_title=meeting_title,
            timezone=timezone,
            expected_participants=int(expected_participants),
        )

        # Canonicalize slots: build list of {display, start_utc, end_utc, tz}
        canonical_slots: List[dict] = []
        try:
            tz = pytz.timezone(timezone or 'US/Mountain')
        except Exception:
            tz = pytz.UTC

        for slot in (time_slots or []):
            display = slot
            start_local = None
            end_local = None

            # Try "Wednesday, August 27, 2025, 3:00 AM - 3:30 AM"
            try:
                parts = display.split(', ')
                if len(parts) >= 4 and ' - ' in parts[3]:
                    month_day = parts[1]
                    year = parts[2]
                    time_range = parts[3]
                    start_time_str = time_range.split(' - ')[0].strip()
                    end_time_str = time_range.split(' - ')[1].strip()

                    date_obj = datetime.strptime(f"{month_day}, {year}", "%B %d, %Y")
                    s_time = datetime.strptime(start_time_str, "%I:%M %p")
                    e_time = datetime.strptime(end_time_str, "%I:%M %p")

                    start_local = date_obj.replace(hour=s_time.hour, minute=s_time.minute, second=0, microsecond=0)
                    end_local = date_obj.replace(hour=e_time.hour, minute=e_time.minute, second=0, microsecond=0)
            except Exception:
                start_local = None
                end_local = None

            # Fallback: "January 15, 2025 at 2:00 PM" (assume 1-hour)
            if start_local is None or end_local is None:
                try:
                    if ' at ' in display:
                        d, t = display.split(' at ')
                        date_obj = datetime.strptime(d, "%B %d, %Y")
                        s_time = datetime.strptime(t, "%I:%M %p")
                        start_local = date_obj.replace(hour=s_time.hour, minute=s_time.minute, second=0, microsecond=0)
                        end_local = start_local + timedelta(hours=1)
                except Exception:
                    start_local = None
                    end_local = None

            if start_local and end_local:
                try:
                    start_aware = tz.localize(start_local)
                    end_aware = tz.localize(end_local)
                except Exception:
                    start_aware = pytz.UTC.localize(start_local)
                    end_aware = pytz.UTC.localize(end_local)

                start_utc = start_aware.astimezone(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
                end_utc = end_aware.astimezone(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
                try:
                    logger.debug(
                        "Canonicalized slot | display='%s' | tz='%s' | start_local='%s' | end_local='%s' | start_utc='%s' | end_utc='%s'",
                        display, timezone, start_aware.isoformat(), end_aware.isoformat(), start_utc, end_utc
                    )
                except Exception:
                    # Logging must never break flow
                    pass
                canonical_slots.append({
                    'display': display,
                    'start_utc': start_utc,
                    'end_utc': end_utc,
                    'tz': timezone,
                })
            else:
                # If parsing fails, preserve as display-only for now
                try:
                    logger.debug("Could not parse slot display='%s' in tz='%s' — storing display-only", display, timezone)
                except Exception:
                    pass
                canonical_slots.append({'display': display, 'start_utc': None, 'end_utc': None, 'tz': timezone})

        # Store canonical JSON
        meeting.time_slots_json = json.dumps(canonical_slots)
        meeting.notification_preferences = notification_preferences or {}
        db.session.add(meeting)
        db.session.commit()
        return token

    def get_meeting(self, token) -> dict | None:
        """Get meeting data by token as dict (with datetime created_at)"""
        m = Meeting.query.filter_by(token=token).first()
        if not m:
            return None
        return {
            'token': m.token,
            'organizer_name': m.organizer_name,
            'organizer_email': m.organizer_email,
            'meeting_title': m.meeting_title,
            'time_slots': m.time_slots,
            'slots_meta': m.slots_meta,
            'timezone': m.timezone,
            'notification_preferences': m.notification_preferences,
            'expected_participants': m.expected_participants,
            'created_at': m.created_at,
        }

    def add_response(self, token, respondent_name, available_slots, no_availability=False) -> None:
        """Add a response to a meeting"""
        m = Meeting.query.filter_by(token=token).first()
        if not m:
            return
        r = Response(
            meeting_id=m.id,
            respondent_name=respondent_name,
            no_availability=bool(no_availability),
        )
        r.available_slots = list(available_slots or [])
        db.session.add(r)
        db.session.commit()

    def get_responses(self, token) -> List[dict]:
        """Get all responses for a meeting as list of dicts"""
        m = Meeting.query.filter_by(token=token).first()
        if not m:
            return []
        results = []
        for r in Response.query.filter_by(meeting_id=m.id).order_by(Response.responded_at.asc()).all():
            results.append({
                'respondent_name': r.respondent_name,
                'available_slots': r.available_slots,
                'no_availability': r.no_availability,
                'responded_at': r.responded_at,
            })
        return results

    def get_best_time_slot(self, token) -> Tuple[str | None, List[str]]:
        """Find the time slot with the most availability"""
        meeting = self.get_meeting(token)
        responses = self.get_responses(token)
        if not meeting or not responses:
            return None, []

        time_slots = meeting['time_slots']
        slot_votes: dict[int, List[str]] = {}
        for response in responses:
            for slot_index in response['available_slots']:
                if 0 <= slot_index < len(time_slots):
                    slot_votes.setdefault(slot_index, []).append(response['respondent_name'])

        if not slot_votes:
            return None, []

        best_slot_index = max(slot_votes.keys(), key=lambda x: len(slot_votes[x]))
        best_slot = time_slots[best_slot_index]
        available_people = slot_votes[best_slot_index]
        return best_slot, available_people

    def has_sent_confirmation(self, token: str, best_slot: str, milestone: str | None = None) -> bool:
        """Check if confirmation has already been sent for a slot and optional milestone.

        Stores in Meeting.notification_preferences JSON under a nested structure:
        {
          "confirmation_sent": {
            "<best_slot>": {
              "half": true,
              "all": true
            }
          }
        }
        """
        m = Meeting.query.filter_by(token=token).first()
        if not m:
            return False
        try:
            prefs = m.notification_preferences
            sent = prefs.get('confirmation_sent', {})
            slot_sends = sent.get(best_slot, {})
            if milestone:
                return bool(slot_sends.get(milestone, False))
            # If any milestone was sent for this slot, consider it sent
            return any(bool(v) for v in slot_sends.values())
        except Exception:
            return False

    def mark_confirmation_sent(self, token: str, best_slot: str, milestone: str | None = None) -> None:
        """Mark in DB that confirmation has been sent for this best_slot and milestone."""
        m = Meeting.query.filter_by(token=token).first()
        if not m:
            return
        prefs = m.notification_preferences
        sent = prefs.get('confirmation_sent', {})
        slot_sends = sent.get(best_slot, {})
        if milestone:
            slot_sends[milestone] = True
        else:
            # Mark both to be safe if milestone not specified
            slot_sends['half'] = True
            slot_sends['all'] = True
        sent[best_slot] = slot_sends
        prefs['confirmation_sent'] = sent
        m.notification_preferences = prefs
        db.session.add(m)
        db.session.commit()


# Global store instance
meeting_store = MeetingStore()
