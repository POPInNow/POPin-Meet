import os
import json
import requests
from datetime import datetime, timedelta
import pytz
from msal import ConfidentialClientApplication
from flask import session

# Microsoft Graph API endpoints
AUTHORITY = "https://login.microsoftonline.com/common"
SCOPE = [
    "https://graph.microsoft.com/Calendars.Read",
    "https://graph.microsoft.com/User.Read",
]
GRAPH_ENDPOINT = "https://graph.microsoft.com/v1.0"

def get_msal_app():
    """Create and return MSAL application"""
    return ConfidentialClientApplication(
        client_id=os.environ.get('MS_CLIENT_ID'),
        client_credential=os.environ.get('MS_CLIENT_SECRET'),
        authority=AUTHORITY
    )

def get_authorization_url(meeting_token):
    """Get the authorization URL for Microsoft OAuth"""
    app = get_msal_app()
    
    # Build redirect URI from production domain
    app_domain = os.environ.get('APP_DOMAIN', os.environ.get('REPLIT_DEV_DOMAIN', 'localhost'))
    redirect_uri = f"https://{app_domain}/msgraph/callback"
    
    # Build authorization URL
    auth_url = app.get_authorization_request_url(
        scopes=SCOPE,
        redirect_uri=redirect_uri,
        state=meeting_token  # Pass meeting token as state
    )
    
    session['msgraph_state'] = meeting_token
    return auth_url

def handle_oauth_callback(authorization_code, state):
    """Handle OAuth callback and return access token"""
    app = get_msal_app()
    
    # Build redirect URI from production domain
    app_domain = os.environ.get('APP_DOMAIN', os.environ.get('REPLIT_DEV_DOMAIN', 'localhost'))
    redirect_uri = f"https://{app_domain}/msgraph/callback"
    
    # Exchange authorization code for tokens
    result = app.acquire_token_by_authorization_code(
        authorization_code,
        scopes=SCOPE,
        redirect_uri=redirect_uri
    )
    
    if "access_token" in result:
        return result["access_token"], state
    else:
        raise Exception(f"Failed to acquire token: {result.get('error_description', 'Unknown error')}")

def get_free_busy_info(access_token, time_slots, timezone: str = 'US/Mountain', slot_ranges_utc=None):
    """
    Get free/busy information for the specified time slots using Microsoft Graph API
    
    Args:
        access_token: Microsoft Graph access token
        time_slots: List of time slot dictionaries with 'date' and 'time' keys
    
    Returns:
        Dictionary mapping time slot indices to availability (True/False)
    """
    try:
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            # Force Graph to return event times in UTC for easy comparison
            'Prefer': 'outlook.timezone="UTC"'
        }
        
        # Convert time slots to UTC ranges (prefer exact UTC ranges if provided)
        time_min = None
        time_max = None
        time_ranges = []  # list of tuples or None for invalid slots
        availability = {i: True for i in range(len(time_slots))}

        if slot_ranges_utc:
            # Expect list aligned with time_slots, with ('YYYY-MM-DDTHH:MM:SSZ', 'YYYY-MM-DDTHH:MM:SSZ') or None
            for i, rng in enumerate(slot_ranges_utc):
                try:
                    if not rng or not rng[0] or not rng[1]:
                        time_ranges.append(None)
                        availability[i] = False
                        continue
                    start_dt = datetime.strptime(rng[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
                    end_dt = datetime.strptime(rng[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
                    time_ranges.append((start_dt, end_dt))
                    if time_min is None or start_dt < time_min:
                        time_min = start_dt
                    if time_max is None or end_dt > time_max:
                        time_max = end_dt
                except Exception:
                    time_ranges.append(None)
                    availability[i] = False
        else:
            # Determine meeting timezone
            try:
                meeting_tz = pytz.timezone(timezone or 'US/Mountain')
            except Exception:
                meeting_tz = pytz.UTC

            for i, slot in enumerate(time_slots):
                # Be defensive: skip invalid/empty, keep index alignment
                try:
                    date_str = (slot.get('date') or '').strip()
                    time_str = (slot.get('time') or '').strip()
                    if not date_str or not time_str:
                        time_ranges.append(None)
                        availability[i] = False
                        continue

                    local_naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                    local_start = meeting_tz.localize(local_naive)
                    # Assume 1-hour meeting duration when exact UTC not provided
                    local_end = local_start + timedelta(hours=1)
                    slot_datetime = local_start.astimezone(pytz.UTC)
                    slot_end = local_end.astimezone(pytz.UTC)

                    time_ranges.append((slot_datetime, slot_end))

                    if time_min is None or slot_datetime < time_min:
                        time_min = slot_datetime
                    if time_max is None or slot_end > time_max:
                        time_max = slot_end
                except Exception:
                    time_ranges.append(None)
                    availability[i] = False
        
        # Query free/busy information using Microsoft Graph calendar/calendarView
        start_time = time_min.isoformat().replace('+00:00', 'Z')
        end_time = time_max.isoformat().replace('+00:00', 'Z')
        
        # Get calendar events in the time range
        calendar_url = f"{GRAPH_ENDPOINT}/me/calendar/calendarView"
        params = {
            'startDateTime': start_time,
            'endDateTime': end_time,
            '$select': 'start,end,showAs'
        }
        try:
            print(f"[DEBUG] Outlook query URL={calendar_url} params={{'startDateTime': '{start_time}', 'endDateTime': '{end_time}', '$select': 'start,end,showAs'}}")
        except Exception:
            pass
        
        response = requests.get(calendar_url, headers=headers, params=params)
        
        if response.status_code != 200:
            print(f"Error fetching calendar data: {response.status_code} - {response.text}")
            return availability  # Return what we have (False for invalid slots)

        events = response.json().get('value', [])
        try:
            print(f"[DEBUG] Outlook events fetched: count={len(events)} for window {start_time} to {end_time}")
            for ev in events:
                try:
                    sa = ev.get('showAs', 'busy')
                    es = ev['start']['dateTime']
                    ee = ev['end']['dateTime']
                    print(f"[DEBUG] Outlook event showAs={sa} start={es} end={ee}")
                except Exception:
                    pass
        except Exception:
            pass

        # Utility to parse Graph datetime strings robustly and ensure tz-aware UTC
        def _parse_graph_dt(dt_str: str) -> datetime:
            # Examples seen: '2025-09-22T08:00:00.0000000' (no Z), or '2025-09-22T08:00:00Z'
            s = dt_str.strip()
            if s.endswith('Z'):
                s = s.replace('Z', '+00:00')
            try:
                dt = datetime.fromisoformat(s)
            except Exception:
                # Fallback: trim fractional seconds to microseconds length
                if '.' in s:
                    head, tail = s.split('.', 1)
                    # keep up to 6 digits for microseconds, drop the rest
                    frac = tail
                    tz_part = ''
                    if '+' in tail or '-' in tail:
                        # split timezone offset
                        for idx, ch in enumerate(tail):
                            if ch in ['+', '-']:
                                frac = tail[:idx]
                                tz_part = tail[idx:]
                                break
                    frac = (frac + '000000')[:6]
                    s2 = head + '.' + frac + tz_part
                    dt = datetime.fromisoformat(s2)
                else:
                    dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                # Treat naive as UTC as we requested UTC via Prefer header
                return dt.replace(tzinfo=pytz.UTC)
            return dt.astimezone(pytz.UTC)

        # Check availability for each time slot (all times are UTC-aware)
        for i, tr in enumerate(time_ranges):
            if tr is None:
                availability[i] = False
                continue
            start_time, end_time = tr
            is_available = True

            for event in events:
                # Only treat 'busy' and 'oof' as blocking. Ignore 'free', 'tentative', 'workingelsewhere', 'unknown'.
                show_as = event.get('showAs', 'busy').lower()
                if show_as not in ['busy', 'oof']:
                    continue

                # Parse event times (Graph should return UTC due to Prefer header)
                event_start_str = event['start']['dateTime']
                event_end_str = event['end']['dateTime']
                event_start = _parse_graph_dt(event_start_str)
                event_end = _parse_graph_dt(event_end_str)

                # Check if the time slot overlaps with any busy event
                if start_time < event_end and end_time > event_start:
                    is_available = False
                    try:
                        print(f"[DEBUG] Outlook overlap slot[{i}] with event {event_start.isoformat()}..{event_end.isoformat()} showAs={show_as}")
                    except Exception:
                        pass
                    break
            
            availability[i] = is_available
            try:
                print(f"[DEBUG] Outlook slot[{i}] {start_time.isoformat()} to {end_time.isoformat()} -> available={is_available}")
            except Exception:
                pass
        
        try:
            print(f"[DEBUG] Outlook availability result: {availability}")
        except Exception:
            pass
        return availability
        
    except Exception as e:
        print(f"Error fetching Microsoft calendar data: {e}")
        # Return a safe default marking slots as unavailable to avoid false positives
        try:
            return {i: False for i in range(len(time_slots))}
        except Exception:
            return {}

def get_user_info(access_token):
    """Get basic user information from Microsoft Graph"""
    try:
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(f"{GRAPH_ENDPOINT}/me", headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching user info: {response.status_code} - {response.text}")
            return {}
            
    except Exception as e:
        print(f"Error fetching user info: {e}")
        return {}