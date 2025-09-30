import os
import json
from datetime import datetime, timedelta
import pytz
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from flask import session, url_for, request

# OAuth 2.0 scopes for Google Calendar and basic profile
# Include profile scopes to allow pre-fill of organizer name/email on the Create page
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'openid',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/userinfo.email',
]

def get_oauth_flow():
    """Create and return Google OAuth flow"""
    # Build redirect URI from production domain
    app_domain = os.environ.get('APP_DOMAIN', os.environ.get('REPLIT_DEV_DOMAIN', 'localhost'))
    redirect_uri = f"https://{app_domain}/oauth2callback"
    
    client_config = {
        "web": {
            "client_id": os.environ.get('GOOGLE_CLIENT_ID'),
            "client_secret": os.environ.get('GOOGLE_CLIENT_SECRET'),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri]
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES
    )
    flow.redirect_uri = redirect_uri
    return flow

def get_authorization_url(meeting_token):
    """Get the authorization URL for Google OAuth"""
    flow = get_oauth_flow()
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        state=meeting_token  # Pass meeting token as state
    )
    session['oauth_state'] = state
    return authorization_url

def handle_oauth_callback(authorization_code, state):
    """Handle OAuth callback and return credentials"""
    flow = get_oauth_flow()
    flow.fetch_token(code=authorization_code)
    
    credentials = flow.credentials
    return credentials, state

def get_calendar_service(credentials):
    """Create and return Google Calendar service"""
    return build('calendar', 'v3', credentials=credentials)

def get_free_busy_info(credentials, time_slots, timezone: str = 'US/Mountain'):
    """
    Get free/busy information for the specified time slots
    
    Args:
        credentials: Google OAuth credentials
        time_slots: List of time slot dictionaries with 'date' and 'time' keys
    
    Returns:
        Dictionary mapping time slot indices to availability (True/False)
    """
    try:
        service = get_calendar_service(credentials)
        
        # Convert time slots to timezone-aware datetime objects
        time_min = None
        time_max = None
        time_ranges = []
        
        # Determine meeting timezone
        try:
            tz = pytz.timezone(timezone or 'US/Mountain')
        except Exception:
            tz = pytz.UTC

        for i, slot in enumerate(time_slots):
            # Parse the date and time
            local_naive = datetime.strptime(f"{slot['date']} {slot['time']}", "%Y-%m-%d %H:%M")
            # Localize to meeting timezone
            local_start = tz.localize(local_naive)
            # Assume 1-hour meeting duration
            local_end = local_start + timedelta(hours=1)
            # Convert to UTC for API and comparison
            start_utc = local_start.astimezone(pytz.UTC)
            end_utc = local_end.astimezone(pytz.UTC)
            
            time_ranges.append((start_utc, end_utc))
            
            if time_min is None or start_utc < time_min:
                time_min = start_utc
            if time_max is None or end_utc > time_max:
                time_max = end_utc
        
        # Query free/busy information
        if time_min is None or time_max is None:
            return {}
            
        freebusy_query = {
            'timeMin': time_min.isoformat().replace('+00:00', 'Z'),
            'timeMax': time_max.isoformat().replace('+00:00', 'Z'),
            'items': [{'id': 'primary'}]  # Primary calendar
        }
        
        freebusy_result = service.freebusy().query(body=freebusy_query).execute()
        busy_times = freebusy_result.get('calendars', {}).get('primary', {}).get('busy', [])
        
        # Check availability for each time slot
        availability = {}
        for i, (start_time, end_time) in enumerate(time_ranges):
            is_available = True
            
            for busy_period in busy_times:
                busy_start = datetime.fromisoformat(busy_period['start'].replace('Z', '+00:00'))
                busy_end = datetime.fromisoformat(busy_period['end'].replace('Z', '+00:00'))
                
                # Check if the time slot overlaps with any busy period
                if (start_time < busy_end and end_time > busy_start):
                    is_available = False
                    break
            
            availability[i] = is_available
        
        return availability
        
    except Exception as e:
        print(f"Error fetching calendar data: {e}")
        return {}

def get_free_busy_info_ranges(credentials, slots, timezone: str = 'US/Mountain'):
    """
    Get free/busy information for explicit start/end slot ranges.

    Args:
        credentials: Google OAuth credentials
        slots: List of dicts: {'date': 'YYYY-MM-DD', 'start': 'HH:MM', 'end': 'HH:MM'}
        timezone: IANA tz name for interpreting provided local times

    Returns:
        Dict mapping slot index (0..n-1) to availability (True/False)
    """
    try:
        service = get_calendar_service(credentials)

        # Determine timezone
        try:
            tz = pytz.timezone(timezone or 'US/Mountain')
        except Exception:
            tz = pytz.UTC

        time_min = None
        time_max = None
        time_ranges = []

        for i, slot in enumerate(slots):
            try:
                date_str = (slot.get('date') or '').strip()
                start_str = (slot.get('start') or '').strip()
                end_str = (slot.get('end') or '').strip()
                if not date_str or not start_str or not end_str:
                    time_ranges.append(None)
                    continue

                local_start_naive = datetime.strptime(f"{date_str} {start_str}", "%Y-%m-%d %H:%M")
                local_end_naive = datetime.strptime(f"{date_str} {end_str}", "%Y-%m-%d %H:%M")
                local_start = tz.localize(local_start_naive)
                local_end = tz.localize(local_end_naive)

                start_utc = local_start.astimezone(pytz.UTC)
                end_utc = local_end.astimezone(pytz.UTC)
                time_ranges.append((start_utc, end_utc))

                if time_min is None or start_utc < time_min:
                    time_min = start_utc
                if time_max is None or end_utc > time_max:
                    time_max = end_utc
            except Exception:
                time_ranges.append(None)

        if time_min is None or time_max is None:
            return {}

        freebusy_query = {
            'timeMin': time_min.isoformat().replace('+00:00', 'Z'),
            'timeMax': time_max.isoformat().replace('+00:00', 'Z'),
            'items': [{'id': 'primary'}]
        }

        freebusy_result = service.freebusy().query(body=freebusy_query).execute()
        busy_times = freebusy_result.get('calendars', {}).get('primary', {}).get('busy', [])

        availability = {}
        for i, tr in enumerate(time_ranges):
            if tr is None:
                availability[i] = False
                continue
            start_time, end_time = tr
            is_available = True
            for busy_period in busy_times:
                busy_start = datetime.fromisoformat(busy_period['start'].replace('Z', '+00:00'))
                busy_end = datetime.fromisoformat(busy_period['end'].replace('Z', '+00:00'))
                if (start_time < busy_end and end_time > busy_start):
                    is_available = False
                    break
            availability[i] = is_available

        return availability
    except Exception as e:
        print(f"Error fetching calendar data (ranges): {e}")
        return {}

def get_user_profile(credentials):
    """Fetch basic user profile (name, email) using Google OAuth2.

    Returns a dict: {'name': str|None, 'email': str|None}
    """
    try:
        oauth2 = build('oauth2', 'v2', credentials=credentials)
        info = oauth2.userinfo().get().execute()
        name = info.get('name') or info.get('given_name')
        email = info.get('email')
        return {'name': name, 'email': email}
    except Exception as e:
        print(f"Error fetching Google user profile: {e}")
        return {'name': None, 'email': None}

def credentials_to_dict(credentials):
    """Convert credentials to dictionary for session storage"""
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

def dict_to_credentials(credentials_dict):
    """Convert dictionary back to credentials object"""
    return Credentials(
        token=credentials_dict['token'],
        refresh_token=credentials_dict.get('refresh_token'),
        token_uri=credentials_dict['token_uri'],
        client_id=credentials_dict['client_id'],
        client_secret=credentials_dict['client_secret'],
        scopes=credentials_dict['scopes']
    )