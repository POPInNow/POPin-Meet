import os
from datetime import datetime, timedelta
from icalendar import Calendar, Event
from urllib.parse import quote
import pytz

def create_ics_calendar(meeting_title, organizer_name, time_slot, location="", timezone="US/Mountain", organizer_email: str | None = None, start_utc: str | None = None, end_utc: str | None = None):
    """Create an .ics calendar file for a meeting"""
    # Parse the time slot format (e.g., "Wednesday, August 27, 2025, 3:00 AM - 3:30 AM")
    try:
        # If canonical UTCs are provided, prefer them to avoid any parsing drift
        if start_utc and end_utc:
            try:
                start_datetime = datetime.strptime(start_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
                end_datetime = datetime.strptime(end_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
                # Keep as aware UTC; many clients accept UTC in ICS
            except Exception:
                start_utc = None
                end_utc = None

        if not (start_utc and end_utc):
            # Split the slot to get date and time parts
            parts = time_slot.split(', ')
            if len(parts) < 4:
                return None
                
            # Extract date components: "Wednesday, August 27, 2025, 3:00 AM - 3:30 AM"
            # parts = ["Wednesday", "August 27", "2025", "3:00 AM - 3:30 AM"]
            month_day = parts[1]  # "August 27"
            year = parts[2]
            time_range = parts[3]  # "3:00 AM - 3:30 AM"
            
            # Split start and end times
            time_parts = time_range.split(' - ')
            if len(time_parts) != 2:
                return None
                
            start_time_str = time_parts[0].strip()
            end_time_str = time_parts[1].strip()
            
            # Parse date from month_day and year
            date_str = f"{month_day}, {year}"  # "August 27, 2025"
            date_obj = datetime.strptime(date_str, "%B %d, %Y")
            
            # Parse start and end times
            start_time_obj = datetime.strptime(start_time_str, "%I:%M %p")
            end_time_obj = datetime.strptime(end_time_str, "%I:%M %p")
            start_datetime = date_obj.replace(hour=start_time_obj.hour, minute=start_time_obj.minute, second=0, microsecond=0)
            end_datetime = date_obj.replace(hour=end_time_obj.hour, minute=end_time_obj.minute, second=0, microsecond=0)
            
            # Apply timezone to datetime objects
            try:
                tz = pytz.timezone(timezone)
                start_datetime = tz.localize(start_datetime)
                end_datetime = tz.localize(end_datetime)
            except Exception as tz_error:
                # Fall back to UTC if timezone is invalid
                print(f"Invalid timezone '{timezone}', using UTC: {tz_error}")
                start_datetime = pytz.UTC.localize(start_datetime)
                end_datetime = pytz.UTC.localize(end_datetime)
        
        # Create calendar
        cal = Calendar()
        cal.add('prodid', '-//POPin Meet//Meeting Scheduler//EN')
        cal.add('version', '2.0')
        cal.add('calscale', 'GREGORIAN')
        
        # Create event
        event = Event()
        event.add('summary', meeting_title)
        # Prefer email for organizer field; name-only may render as unknown in some clients
        organizer_value = organizer_email if organizer_email else organizer_name
        # Ensure organizer field uses a mailto URI if email provided
        if organizer_email:
            event.add('organizer', f"mailto:{organizer_email}")
            # Optionally include CN (common name) parameter if library supports
            try:
                event['organizer'].params['cn'] = organizer_name
            except Exception:
                pass
        else:
            event.add('organizer', f"mailto:{organizer_value}")
        event.add('dtstart', start_datetime)
        event.add('dtend', end_datetime)
        event.add('dtstamp', datetime.now())
        event.add('uid', f"{start_datetime.isoformat()}@popinmeet.com")
        
        if location:
            event.add('location', location)
        
        cal.add_component(event)
        
        return cal.to_ical().decode('utf-8')
        
    except Exception as e:
        print(f"Error creating ICS calendar: {e}")
        return None

def get_google_calendar_url(meeting_title, time_slot, location="", timezone="US/Mountain", start_utc: str | None = None, end_utc: str | None = None):
    """Generate Google Calendar add event URL"""
    try:
        # Prefer canonical UTC if available
        if start_utc and end_utc:
            start_dt_utc = datetime.strptime(start_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
            end_dt_utc = datetime.strptime(end_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
        else:
            # Parse time slot format: "Wednesday, August 27, 2025, 3:00 AM - 3:30 AM"
            parts = time_slot.split(', ')
            if len(parts) < 4:
                return None
            month_day = parts[1]
            year = parts[2]
            time_range = parts[3]
            time_parts = time_range.split(' - ')
            if len(time_parts) != 2:
                return None
            start_time_str = time_parts[0].strip()
            end_time_str = time_parts[1].strip()
            date_str = f"{month_day}, {year}"
            date_obj = datetime.strptime(date_str, "%B %d, %Y")
            start_time_obj = datetime.strptime(start_time_str, "%I:%M %p")
            end_time_obj = datetime.strptime(end_time_str, "%I:%M %p")
            start_datetime = date_obj.replace(hour=start_time_obj.hour, minute=start_time_obj.minute)
            end_datetime = date_obj.replace(hour=end_time_obj.hour, minute=end_time_obj.minute)
            try:
                tz = pytz.timezone(timezone)
                start_datetime = tz.localize(start_datetime)
                end_datetime = tz.localize(end_datetime)
            except Exception:
                start_datetime = pytz.UTC.localize(start_datetime)
                end_datetime = pytz.UTC.localize(end_datetime)
            start_dt_utc = start_datetime.astimezone(pytz.UTC)
            end_dt_utc = end_datetime.astimezone(pytz.UTC)

        # Format for Google Calendar (UTC format)
        start_formatted = start_dt_utc.strftime("%Y%m%dT%H%M%SZ")
        end_formatted = end_dt_utc.strftime("%Y%m%dT%H%M%SZ")
        
        # Build URL
        base_url = "https://calendar.google.com/calendar/render"
        params = {
            'action': 'TEMPLATE',
            'text': meeting_title,
            'dates': f"{start_formatted}/{end_formatted}",
            'details': f"Meeting organized via POPin Meet",
            'location': location
        }
        
        url_params = "&".join([f"{k}={quote(str(v))}" for k, v in params.items() if v])
        return f"{base_url}?{url_params}"
        
    except Exception as e:
        print(f"Error creating Google Calendar URL: {e}")
        return None

def get_outlook_calendar_url(meeting_title, time_slot, location="", timezone="US/Mountain", start_utc: str | None = None, end_utc: str | None = None):
    """Generate Outlook (personal/live.com) add event deeplink.

    Use UTC Z timestamps and include rru/path for broader compatibility with consumer Outlook.
    """
    try:
        # Compute start/end in UTC
        if start_utc and end_utc:
            start_dt_utc = datetime.strptime(start_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
            end_dt_utc = datetime.strptime(end_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
        else:
            parts = time_slot.split(', ')
            if len(parts) < 4:
                return None
            month_day = parts[1]
            year = parts[2]
            time_range = parts[3]
            time_parts = time_range.split(' - ')
            if len(time_parts) != 2:
                return None
            start_time_str = time_parts[0].strip()
            end_time_str = time_parts[1].strip()
            date_str = f"{month_day}, {year}"
            date_obj = datetime.strptime(date_str, "%B %d, %Y")
            start_time_obj = datetime.strptime(start_time_str, "%I:%M %p")
            end_time_obj = datetime.strptime(end_time_str, "%I:%M %p")
            start_local = date_obj.replace(hour=start_time_obj.hour, minute=start_time_obj.minute)
            end_local = date_obj.replace(hour=end_time_obj.hour, minute=end_time_obj.minute)
            try:
                tz = pytz.timezone(timezone)
                start_local = tz.localize(start_local)
                end_local = tz.localize(end_local)
            except Exception:
                start_local = pytz.UTC.localize(start_local)
                end_local = pytz.UTC.localize(end_local)
            start_dt_utc = start_local.astimezone(pytz.UTC)
            end_dt_utc = end_local.astimezone(pytz.UTC)

        # Outlook personal is picky with offsets; send Zulu format explicitly
        start_formatted = start_dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_formatted = end_dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Build URL (deeplink compose) with rru/path hints
        base_url = "https://outlook.live.com/calendar/0/deeplink/compose"
        params = {
            'path': '/calendar/action/compose',
            'rru': 'addevent',
            'subject': meeting_title,
            'startdt': start_formatted,
            'enddt': end_formatted,
            'allday': 'false',
            'body': "Meeting organized via POPin Meet",
            'location': location,
        }

        url_params = "&".join([f"{k}={quote(str(v))}" for k, v in params.items() if v])
        return f"{base_url}?{url_params}"

    except Exception as e:
        print(f"Error creating Outlook Calendar URL: {e}")
        return None

def get_outlook365_calendar_url(meeting_title, time_slot, location="", timezone="US/Mountain", start_utc: str | None = None, end_utc: str | None = None):
    """Generate Outlook 365 (office.com) calendar add event URL"""
    try:
        if start_utc and end_utc:
            start_datetime = datetime.strptime(start_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
            end_datetime = datetime.strptime(end_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
        else:
            parts = time_slot.split(', ')
            if len(parts) < 4:
                return None
            month_day = parts[1]
            year = parts[2]
            time_range = parts[3]
            time_parts = time_range.split(' - ')
            if len(time_parts) != 2:
                return None
            start_time_str = time_parts[0].strip()
            end_time_str = time_parts[1].strip()
            date_str = f"{month_day}, {year}"
            date_obj = datetime.strptime(date_str, "%B %d, %Y")
            start_time_obj = datetime.strptime(start_time_str, "%I:%M %p")
            end_time_obj = datetime.strptime(end_time_str, "%I:%M %p")
            start_datetime = date_obj.replace(hour=start_time_obj.hour, minute=start_time_obj.minute)
            end_datetime = date_obj.replace(hour=end_time_obj.hour, minute=end_time_obj.minute)
            try:
                tz = pytz.timezone(timezone)
                start_datetime = tz.localize(start_datetime)
                end_datetime = tz.localize(end_datetime)
            except Exception:
                start_datetime = pytz.UTC.localize(start_datetime)
                end_datetime = pytz.UTC.localize(end_datetime)

        # Use ISO format for office.com deeplink
        start_formatted = start_datetime.isoformat()
        end_formatted = end_datetime.isoformat()
        
        base_url = "https://outlook.office.com/calendar/0/deeplink/compose"
        params = {
            'subject': meeting_title,
            'startdt': start_formatted,
            'enddt': end_formatted,
            'body': "Meeting organized via POPin Meet",
            'location': location
        }
        url_params = "&".join([f"{k}={quote(str(v))}" for k, v in params.items() if v])
        return f"{base_url}?{url_params}"
    except Exception as e:
        print(f"Error creating Outlook 365 Calendar URL: {e}")
        return None