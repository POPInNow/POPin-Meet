from flask import render_template, request, redirect, url_for, flash, session, Response, jsonify
import os
from app import app
from models import meeting_store
from datetime import datetime, timedelta
import google_calendar
import microsoft_calendar
import calendar_utils
import email_utils
import notification_utils
import pytz

@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')

# --- Pre-create calendar connect flows (used on /create page) ---

@app.route('/connect_calendar_precreate')
def connect_calendar_precreate():
    """Start Google Calendar OAuth flow for pre-create context (no meeting token)."""
    try:
        authorization_url = google_calendar.get_authorization_url('precreate')
        return redirect(authorization_url)
    except Exception:
        flash("Unable to connect to Google Calendar. Please try again.", 'danger')
        return redirect(url_for('create_meeting'))

@app.route('/connect_outlook_precreate')
def connect_outlook_precreate():
    """Start Microsoft Outlook OAuth flow for pre-create context (no meeting token)."""
    try:
        authorization_url = microsoft_calendar.get_authorization_url('precreate')
        return redirect(authorization_url)
    except Exception:
        flash("Unable to connect to Outlook calendar. Please try again.", 'danger')
        return redirect(url_for('create_meeting'))

@app.route('/disconnect_precreate/<provider>')
def disconnect_precreate(provider):
    """Disconnect pre-create calendar provider and clear related profile if applicable."""
    try:
        if provider == 'google':
            session.pop('google_credentials_precreate', None)
            flash("Disconnected Google Calendar.", 'info')
        elif provider == 'outlook':
            session.pop('outlook_token_precreate', None)
            flash("Disconnected Outlook Calendar.", 'info')
        # If neither provider connected, clear active provider and profile
        if not session.get('google_credentials_precreate') and not session.get('outlook_token_precreate'):
            session.pop('precreate_av_source', None)
            # Preserve profile if user wants to keep autofill; comment out next line to preserve
            # session.pop('precreate_profile', None)
    except Exception:
        pass
    return redirect(url_for('create_meeting'))

@app.route('/api/precreate/set_provider', methods=['POST'])
def api_precreate_set_provider():
    data = request.get_json(silent=True) or {}
    provider = (data.get('provider') or '').strip().lower()
    if provider not in {'google', 'outlook'}:
        return jsonify({'ok': False, 'error': 'invalid_provider'}), 400
    if provider == 'google' and not session.get('google_credentials_precreate'):
        return jsonify({'ok': False, 'error': 'not_connected'}), 400
    if provider == 'outlook' and not session.get('outlook_token_precreate'):
        return jsonify({'ok': False, 'error': 'not_connected'}), 400
    session['precreate_av_source'] = provider
    return jsonify({'ok': True, 'provider': provider})

@app.route('/api/precreate/freebusy', methods=['POST'])
def api_precreate_freebusy():
    """Return availability for proposed slots on the create page.

    Expected JSON body: {
      "provider": "google"|"outlook" (optional),
      "timezone": "IANA/TZ",
      "slots": [ {"date": "YYYY-MM-DD", "start": "HH:MM", "end": "HH:MM"}, ... ]
    }
    """
    payload = request.get_json(silent=True) or {}
    requested_provider = (payload.get('provider') or '').strip().lower()
    timezone = (payload.get('timezone') or 'US/Mountain').strip()
    slots = payload.get('slots') or []

    # Determine active provider per best practice:
    # - If explicitly provided and connected, use it (and persist choice).
    # - Else if session precreate_av_source is set and connected, use it.
    # - Else if exactly one provider connected, use that.
    # - Else require selection.
    google_connected = bool(session.get('google_credentials_precreate'))
    outlook_connected = bool(session.get('outlook_token_precreate'))

    active_provider = None
    if requested_provider in {'google', 'outlook'}:
        if requested_provider == 'google' and google_connected:
            active_provider = 'google'
        elif requested_provider == 'outlook' and outlook_connected:
            active_provider = 'outlook'
        # Persist only if valid
        if active_provider:
            session['precreate_av_source'] = active_provider

    if not active_provider:
        sess_provider = (session.get('precreate_av_source') or '').strip().lower()
        if sess_provider == 'google' and google_connected:
            active_provider = 'google'
        elif sess_provider == 'outlook' and outlook_connected:
            active_provider = 'outlook'

    if not active_provider:
        if google_connected ^ outlook_connected:  # exactly one
            active_provider = 'google' if google_connected else 'outlook'

    if not active_provider:
        return jsonify({'ok': False, 'error': 'no_provider_selected'}), 400

    try:
        if active_provider == 'google':
            credentials_dict = session.get('google_credentials_precreate')
            if not credentials_dict:
                return jsonify({'ok': False, 'error': 'not_connected'}), 400
            credentials = google_calendar.dict_to_credentials(credentials_dict)
            availability = google_calendar.get_free_busy_info_ranges(credentials, slots, timezone=timezone)
        else:  # outlook
            access_token = session.get('outlook_token_precreate')
            if not access_token:
                return jsonify({'ok': False, 'error': 'not_connected'}), 400
            # Build time_slots (start times) and exact UTC ranges for precision
            time_slots = []
            slot_ranges_utc = []
            try:
                tz = pytz.timezone(timezone or 'US/Mountain')
            except Exception:
                tz = pytz.UTC
            for s in slots:
                try:
                    date_str = (s.get('date') or '').strip()
                    start_str = (s.get('start') or '').strip()
                    end_str = (s.get('end') or '').strip()
                    if not date_str or not start_str or not end_str:
                        time_slots.append({'date': '', 'time': ''})
                        slot_ranges_utc.append(None)
                        continue
                    start_local = tz.localize(datetime.strptime(f"{date_str} {start_str}", "%Y-%m-%d %H:%M"))
                    end_local = tz.localize(datetime.strptime(f"{date_str} {end_str}", "%Y-%m-%d %H:%M"))
                    start_utc = start_local.astimezone(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
                    end_utc = end_local.astimezone(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
                    time_slots.append({'date': date_str, 'time': start_str})
                    slot_ranges_utc.append((start_utc, end_utc))
                except Exception:
                    time_slots.append({'date': '', 'time': ''})
                    slot_ranges_utc.append(None)
            availability = microsoft_calendar.get_free_busy_info(
                access_token,
                time_slots,
                timezone=timezone,
                slot_ranges_utc=slot_ranges_utc,
            )
        return jsonify({'ok': True, 'provider': active_provider, 'availability': availability})
    except Exception as e:
        print(f"precreate freebusy error: {e}")
        return jsonify({'ok': False, 'error': 'internal'}), 500

@app.route('/create', methods=['GET', 'POST'])
def create_meeting():
    """Create a new meeting"""
    # Pre-create connection/profile context for both GET and POST paths
    precreate_google_connected = bool(session.get('google_credentials_precreate'))
    precreate_outlook_connected = bool(session.get('outlook_token_precreate'))
    precreate_profile = session.get('precreate_profile', {})
    precreate_active_provider = session.get('precreate_av_source')  # optional

    if request.method == 'POST':
        # Get form data
        organizer_name = request.form.get('organizer_name', '').strip()
        meeting_title = request.form.get('meeting_title', '').strip()
        expected_participants = request.form.get('expected_participants', '').strip()
        timezone = request.form.get('timezone', 'US/Mountain').strip()
        
        # Get notification preferences
        notification_methods = request.form.getlist('notification_methods')
        # Enable Email, Slack, and SMS (WhatsApp remains disabled for now)
        allowed_methods = [m for m in notification_methods if m in {'email', 'slack', 'sms'}]
        notification_preferences = {
            'methods': allowed_methods,
            'sms_phone': request.form.get('sms_phone', '').strip() if 'sms' in allowed_methods else '',
            'whatsapp_phone': '',  # disabled for now
            'slack_webhook': request.form.get('slack_webhook', '').strip() if 'slack' in allowed_methods else '',
            'email_address': request.form.get('email_address', '').strip() if 'email' in allowed_methods else ''
        }
        
        # Build time slots server-side in the selected timezone to avoid browser TZ drift
        # We read raw values (date_i, start_time_i, end_time_i) and construct the display string here.
        time_slots = []
        try:
            tz = pytz.timezone(timezone or 'US/Mountain')
        except Exception:
            tz = pytz.UTC
        for i in range(1, 3 + 1):  # Support up to 3 time slots
            date_raw = (request.form.get(f'date_{i}') or '').strip()           # YYYY-MM-DD
            start_raw = (request.form.get(f'start_time_{i}') or '').strip()    # HH:MM (24h)
            end_raw = (request.form.get(f'end_time_{i}') or '').strip()        # HH:MM (24h)
            if not date_raw or not start_raw or not end_raw:
                continue
            try:
                # Parse local date (no timezone) and times
                y, m, d = [int(p) for p in date_raw.split('-')]
                start_h, start_m = [int(p) for p in start_raw.split(':')]
                end_h, end_m = [int(p) for p in end_raw.split(':')]

                date_obj = datetime(y, m, d)
                start_local = date_obj.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
                end_local = date_obj.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

                # Localize using the selected timezone (not the browser timezone)
                start_aware = tz.localize(start_local)
                end_aware = tz.localize(end_local)

                # Format display consistently: "Wednesday, August 27, 2025, 3:00 AM - 3:30 AM"
                day_name = start_aware.strftime('%A')
                month_day = start_aware.strftime('%B %d').lstrip('0').replace(' 0', ' ')
                year_str = start_aware.strftime('%Y')
                start_disp = start_aware.strftime('%-I:%M %p') if hasattr(start_aware, 'strftime') else start_aware.strftime('%I:%M %p')
                end_disp = end_aware.strftime('%-I:%M %p') if hasattr(end_aware, 'strftime') else end_aware.strftime('%I:%M %p')
                # Windows strftime may not support %-I; provide fallback to remove leading zero
                if start_disp.startswith('0'):
                    start_disp = start_disp[1:]
                if end_disp.startswith('0'):
                    end_disp = end_disp[1:]
                display = f"{day_name}, {month_day}, {year_str}, {start_disp} - {end_disp}"
                time_slots.append(display)
            except Exception:
                # As a fallback, if parsing fails, keep any client-sent formatted slot
                slot = (request.form.get(f'time_slot_{i}') or '').strip()
                if slot:
                    time_slots.append(slot)
        
        # Detect duplicates strictly by same date + start (regardless of end)
        start_keys = []
        for i in range(1, 3 + 1):
            d = (request.form.get(f'date_{i}') or '').strip()
            s = (request.form.get(f'start_time_{i}') or '').strip()
            if d and s:
                start_keys.append((i, f"{d}|{s}"))
        seen = {}
        duplicate_pairs = []  # list of tuples (first_slot_num, dup_slot_num)
        for idx, key in start_keys:
            if key in seen:
                duplicate_pairs.append((seen[key], idx))
            else:
                seen[key] = idx

        # Validation
        errors = []
        if not organizer_name:
            errors.append("Organizer name is required")
        if not meeting_title:
            errors.append("Meeting title is required")
        if not expected_participants:
            errors.append("Expected participant count is required")
        else:
            try:
                expected_participants = int(expected_participants)
                if expected_participants < 2 or expected_participants > 50:
                    errors.append("Expected participants must be between 2 and 50")
            except ValueError:
                errors.append("Expected participants must be a valid number")
        if len(time_slots) < 2:
            errors.append("At least 2 time slots are required")
        if len(time_slots) > 3:
            errors.append("Maximum 3 time slots allowed")
        # Add duplicate errors (reference human-friendly slot numbers)
        for a, b in duplicate_pairs:
            errors.append(f"Time Slot {b} duplicates Time Slot {a} (same date and start); please choose a different time")
        if not allowed_methods:
            errors.append("Please select at least one notification method")
        
        # Validate notification-specific fields
        # Validate selected channels (WhatsApp disabled)
        if 'sms' in allowed_methods and not notification_preferences['sms_phone']:
            errors.append("Phone number is required for SMS notifications")
        if 'slack' in allowed_methods and not notification_preferences['slack_webhook']:
            errors.append("Slack webhook URL is required for Slack notifications")
        if 'email' in allowed_methods and not notification_preferences['email_address']:
            errors.append("Email address is required for email notifications")
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('create_meeting.html',
                                   precreate_google_connected=precreate_google_connected,
                                   precreate_outlook_connected=precreate_outlook_connected,
                                   precreate_profile=precreate_profile,
                                   precreate_active_provider=precreate_active_provider)
        
        # Create the meeting  
        organizer_email = notification_preferences.get('email_address', '')
        token = meeting_store.create_meeting(organizer_name, organizer_email, meeting_title, time_slots, timezone, notification_preferences, int(expected_participants))

        # Best practice for UX: if organizer connected a calendar in pre-create flow,
        # carry over those credentials to the specific meeting session so subsequent pages
        # (respond/summary) have calendar features ready.
        try:
            if session.get('google_credentials_precreate'):
                session[f'google_credentials_{token}'] = session.get('google_credentials_precreate')
            if session.get('outlook_token_precreate'):
                session[f'outlook_token_{token}'] = session.get('outlook_token_precreate')
        except Exception:
            pass

        return redirect(url_for('meeting_created', token=token))
    
    return render_template('create_meeting.html',
                           precreate_google_connected=precreate_google_connected,
                           precreate_outlook_connected=precreate_outlook_connected,
                           precreate_profile=precreate_profile,
                           precreate_active_provider=precreate_active_provider)

@app.route('/meeting/<token>/created')
def meeting_created(token):
    """Show meeting creation confirmation with shareable link"""
    meeting = meeting_store.get_meeting(token)
    if not meeting:
        flash("Meeting not found", 'danger')
        return redirect(url_for('index'))
    
    share_url = url_for('respond_meeting', token=token, _external=True)
    return render_template('meeting_created.html', meeting=meeting, share_url=share_url)

@app.route('/s/<token>', methods=['GET', 'POST'])
def respond_meeting(token):
    """Respond to a meeting invitation"""
    meeting = meeting_store.get_meeting(token)
    if not meeting:
        flash("Meeting not found", 'danger')
        return redirect(url_for('index'))
    
    # Check if user has Google Calendar connected and get pre-selected slots
    google_availability = {}
    google_connected = False
    if f'google_credentials_{token}' in session:
        try:
            credentials_dict = session[f'google_credentials_{token}']
            credentials = google_calendar.dict_to_credentials(credentials_dict)
            
            # Build meeting time slots for calendar check using canonical UTCs if available
            time_slots = []
            slots_meta = meeting.get('slots_meta') or []
            tz_name = meeting.get('timezone', 'US/Mountain')
            try:
                tz = pytz.timezone(tz_name or 'US/Mountain')
            except Exception:
                tz = pytz.UTC
            if slots_meta:
                for item in slots_meta:
                    try:
                        start_utc = item.get('start_utc')
                        if start_utc:
                            start_dt_utc = datetime.strptime(start_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
                            start_local = start_dt_utc.astimezone(tz)
                            time_slots.append({'date': start_local.strftime("%Y-%m-%d"), 'time': start_local.strftime("%H:%M")})
                        else:
                            # Fallback to display parsing if canonical missing
                            raise ValueError('missing canonical start_utc')
                    except Exception:
                        # Final fallback: parse display string for this slot
                        slot_display = item.get('display') if isinstance(item, dict) else str(item)
                        parsed = False
                        try:
                            if ' at ' in slot_display:
                                parts = slot_display.split(' at ')
                                date_str = parts[0]
                                time_str = parts[1]
                                date_obj = datetime.strptime(date_str, "%B %d, %Y")
                                time_obj = datetime.strptime(time_str, "%I:%M %p")
                                time_slots.append({'date': date_obj.strftime("%Y-%m-%d"), 'time': time_obj.strftime("%H:%M")})
                                parsed = True
                            else:
                                parts = slot_display.split(', ')
                                if len(parts) >= 4 and ' - ' in parts[3]:
                                    month_day = parts[1]
                                    year = parts[2]
                                    start_time_str = parts[3].split(' - ')[0].strip()
                                    date_str = f"{month_day}, {year}"
                                    date_obj = datetime.strptime(date_str, "%B %d, %Y")
                                    time_obj = datetime.strptime(start_time_str, "%I:%M %p")
                                    time_slots.append({'date': date_obj.strftime("%Y-%m-%d"), 'time': time_obj.strftime("%H:%M")})
                                    parsed = True
                        except Exception:
                            parsed = False
                        if not parsed:
                            time_slots.append({'date': '', 'time': ''})
            else:
                # Legacy fallback when only display strings are present
                for slot in meeting['time_slots']:
                    parsed = False
                    try:
                        if ' at ' in slot:
                            parts = slot.split(' at ')
                            date_str = parts[0]
                            time_str = parts[1]
                            date_obj = datetime.strptime(date_str, "%B %d, %Y")
                            time_obj = datetime.strptime(time_str, "%I:%M %p")
                            time_slots.append({'date': date_obj.strftime("%Y-%m-%d"), 'time': time_obj.strftime("%H:%M")})
                            parsed = True
                        else:
                            parts = slot.split(', ')
                            if len(parts) >= 4 and ' - ' in parts[3]:
                                month_day = parts[1]
                                year = parts[2]
                                start_time_str = parts[3].split(' - ')[0].strip()
                                date_str = f"{month_day}, {year}"
                                date_obj = datetime.strptime(date_str, "%B %d, %Y")
                                time_obj = datetime.strptime(start_time_str, "%I:%M %p")
                                time_slots.append({'date': date_obj.strftime("%Y-%m-%d"), 'time': time_obj.strftime("%H:%M")})
                                parsed = True
                    except Exception:
                        parsed = False
                    if not parsed:
                        time_slots.append({'date': '', 'time': ''})
            
            if time_slots:
                google_availability = google_calendar.get_free_busy_info(
                    credentials,
                    time_slots,
                    timezone=meeting.get('timezone', 'US/Mountain')
                )
                google_connected = True
        except Exception as e:
            print(f"Error checking calendar availability: {e}")
            # Remove invalid credentials
            session.pop(f'google_credentials_{token}', None)
    
    # Check if user has Microsoft Outlook connected and get pre-selected slots
    outlook_availability = {}
    outlook_connected = False
    if f'outlook_token_{token}' in session:
        try:
            access_token = session[f'outlook_token_{token}']
            
            # Build meeting time slots for calendar check using canonical UTCs if available (same as Google)
            time_slots = []
            slot_ranges_utc = []  # Parallel to time_slots: tuples (start_utc, end_utc) or None
            slots_meta = meeting.get('slots_meta') or []
            tz_name = meeting.get('timezone', 'US/Mountain')
            try:
                tz = pytz.timezone(tz_name or 'US/Mountain')
            except Exception:
                tz = pytz.UTC
            if slots_meta:
                for item in slots_meta:
                    try:
                        start_utc = item.get('start_utc')
                        end_utc = item.get('end_utc')
                        if start_utc:
                            start_dt_utc = datetime.strptime(start_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
                            start_local = start_dt_utc.astimezone(tz)
                            time_slots.append({'date': start_local.strftime("%Y-%m-%d"), 'time': start_local.strftime("%H:%M")})
                            # Push exact range. If end_utc missing, assume 30-minute duration from start.
                            if not end_utc:
                                end_dt_utc = (start_dt_utc + timedelta(minutes=30))
                                end_utc = end_dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
                            slot_ranges_utc.append((start_utc, end_utc))
                        else:
                            raise ValueError('missing canonical start_utc')
                    except Exception:
                        slot_display = item.get('display') if isinstance(item, dict) else str(item)
                        parsed = False
                        try:
                            if ' at ' in slot_display:
                                parts = slot_display.split(' at ')
                                date_str = parts[0]
                                time_str = parts[1]
                                date_obj = datetime.strptime(date_str, "%B %d, %Y")
                                time_obj = datetime.strptime(time_str, "%I:%M %p")
                                time_slots.append({'date': date_obj.strftime("%Y-%m-%d"), 'time': time_obj.strftime("%H:%M")})
                                parsed = True
                            else:
                                parts = slot_display.split(', ')
                                if len(parts) >= 4 and ' - ' in parts[3]:
                                    month_day = parts[1]
                                    year = parts[2]
                                    start_time_str = parts[3].split(' - ')[0].strip()
                                    date_str = f"{month_day}, {year}"
                                    date_obj = datetime.strptime(date_str, "%B %d, %Y")
                                    time_obj = datetime.strptime(start_time_str, "%I:%M %p")
                                    time_slots.append({'date': date_obj.strftime("%Y-%m-%d"), 'time': time_obj.strftime("%H:%M")})
                                    parsed = True
                        except Exception:
                            parsed = False
                        if not parsed:
                            time_slots.append({'date': '', 'time': ''})
                        # No canonical UTCs in this path
                        slot_ranges_utc.append(None)
            else:
                for slot in meeting['time_slots']:
                    parsed = False
                    try:
                        if ' at ' in slot:
                            parts = slot.split(' at ')
                            date_str = parts[0]
                            time_str = parts[1]
                            date_obj = datetime.strptime(date_str, "%B %d, %Y")
                            time_obj = datetime.strptime(time_str, "%I:%M %p")
                            time_slots.append({'date': date_obj.strftime("%Y-%m-%d"), 'time': time_obj.strftime("%H:%M")})
                            parsed = True
                        else:
                            parts = slot.split(', ')
                            if len(parts) >= 4 and ' - ' in parts[3]:
                                month_day = parts[1]
                                year = parts[2]
                                start_time_str = parts[3].split(' - ')[0].strip()
                                date_str = f"{month_day}, {year}"
                                date_obj = datetime.strptime(date_str, "%B %d, %Y")
                                time_obj = datetime.strptime(start_time_str, "%I:%M %p")
                                time_slots.append({'date': date_obj.strftime("%Y-%m-%d"), 'time': time_obj.strftime("%H:%M")})
                                parsed = True
                    except Exception:
                        parsed = False
                    if not parsed:
                        time_slots.append({'date': '', 'time': ''})
                    slot_ranges_utc.append(None)
            
            if time_slots:
                try:
                    print(f"[DEBUG] token={token} tz={meeting.get('timezone')} outlook time_slots={time_slots} slot_ranges_utc={slot_ranges_utc}")
                except Exception:
                    pass
                outlook_availability = microsoft_calendar.get_free_busy_info(
                    access_token,
                    time_slots,
                    timezone=meeting.get('timezone', 'US/Mountain'),
                    slot_ranges_utc=slot_ranges_utc
                )
                outlook_connected = True
                try:
                    print(f"[DEBUG] token={token} outlook_availability={outlook_availability}")
                except Exception:
                    pass
        except Exception as e:
            print(f"Error checking Outlook calendar availability: {e}")
            # Remove invalid token
            session.pop(f'outlook_token_{token}', None)
    
    if request.method == 'POST':
        respondent_name = request.form.get('respondent_name', '').strip()
        available_slots = []
        no_availability = request.form.get('no_availability')
        
        # Get selected time slots
        for i in range(len(meeting['time_slots'])):
            if request.form.get(f'slot_{i}'):
                available_slots.append(i)
        
        # Validation
        errors = []
        if not respondent_name:
            errors.append("Your name is required")
        if not available_slots and not no_availability:
            errors.append("Please select at least one available time slot or indicate that none work for you")
        
        # Check if this person has already responded
        existing_responses = meeting_store.get_responses(token)
        for response in existing_responses:
            if response['respondent_name'].lower() == respondent_name.lower():
                errors.append("You have already responded to this meeting")
                break
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('respond_meeting.html', meeting=meeting, 
                                 google_availability=google_availability, 
                                 outlook_availability=outlook_availability,
                                 google_connected=google_connected,
                                 outlook_connected=outlook_connected, 
                                 token=token)
        
        # Add the response
        meeting_store.add_response(token, respondent_name, available_slots, bool(no_availability))
        
        # Per new policy: do not send SMS/Slack/WhatsApp/email after each response.
        # Notifications are only sent on final confirmation within meeting_summary.
        
        # Per-response organizer email disabled per updated policy
        # (We only send confirmation emails at milestones now.)
        
        flash("Your response has been recorded successfully!", 'success')
        
        return redirect(url_for('meeting_summary', token=token))
    
    return render_template('respond_meeting.html', meeting=meeting, 
                         google_availability=google_availability, 
                         outlook_availability=outlook_availability,
                         google_connected=google_connected,
                         outlook_connected=outlook_connected, 
                         token=token)

@app.route('/meeting/<token>/summary')
def meeting_summary(token):
    """Show meeting summary with responses and best time"""
    meeting = meeting_store.get_meeting(token)
    if not meeting:
        flash("Meeting not found", 'danger')
        return redirect(url_for('index'))
    
    responses = meeting_store.get_responses(token)
    best_slot, available_people = meeting_store.get_best_time_slot(token)
    
    # Calculate availability for each time slot
    slot_availability = []
    for i, slot in enumerate(meeting['time_slots']):
        available_for_slot = []
        for response in responses:
            if i in response['available_slots']:
                available_for_slot.append(response['respondent_name'])
        slot_availability.append({
            'slot': slot,
            'available_people': available_for_slot,
            'count': len(available_for_slot)
        })
    
    # Count people who said none of the times work
    no_availability_responses = []
    for response in responses:
        if response.get('no_availability', False):
            no_availability_responses.append(response['respondent_name'])
    
    # Generate calendar URLs using best slot if available; otherwise fall back to first slot
    google_calendar_url = None
    outlook_calendar_url = None
    outlook_calendar_url_office = None
    selected_slot = best_slot if best_slot else (meeting['time_slots'][0] if meeting.get('time_slots') else None)
    if selected_slot:
        # Try to find canonical UTCs for the selected slot to avoid re-parsing display strings
        start_utc = None
        end_utc = None
        try:
            for item in (meeting.get('slots_meta') or []):
                if isinstance(item, dict) and item.get('display') == selected_slot:
                    start_utc = item.get('start_utc')
                    end_utc = item.get('end_utc')
                    break
        except Exception:
            start_utc = None
            end_utc = None

        google_calendar_url = calendar_utils.get_google_calendar_url(
            meeting['meeting_title'], selected_slot, timezone=meeting.get('timezone', 'US/Mountain'), start_utc=start_utc, end_utc=end_utc
        )
        outlook_calendar_url = calendar_utils.get_outlook_calendar_url(
            meeting['meeting_title'], selected_slot, timezone=meeting.get('timezone', 'US/Mountain'), start_utc=start_utc, end_utc=end_utc
        )
        # Also provide an Outlook 365 (office.com) variant for work accounts
        try:
            outlook_calendar_url_office = calendar_utils.get_outlook365_calendar_url(
                meeting['meeting_title'], selected_slot, timezone=meeting.get('timezone', 'US/Mountain'), start_utc=start_utc, end_utc=end_utc
            )
        except Exception:
            outlook_calendar_url_office = None
        
        # Confirmation notifications only when all expected participants have responded
        try:
            total_responses = len(responses)
            expected_participants = meeting.get('expected_participants', 5)
            milestone = None
            if expected_participants and total_responses >= expected_participants:
                milestone = 'all'

            # Allow forcing notifications during testing via query param or env var
            force_notify = (request.args.get('force_notify') == '1') or (
                str(os.environ.get('NOTIFICATION_ALWAYS_SEND', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
            )

            if milestone and (force_notify or not meeting_store.has_sent_confirmation(token, best_slot, milestone)):
                notification_preferences = meeting.get('notification_preferences', {})
                methods = notification_preferences.get('methods', ['email'])

                any_success = False
                # Send email if selected
                if 'email' in methods:
                    # Prefer canonical UTCs for robust calendar links and ICS
                    email_start_utc = start_utc
                    email_end_utc = end_utc
                    sent_ok = email_utils.send_confirmation_email(
                        meeting['organizer_email'],
                        meeting['organizer_name'],
                        meeting['meeting_title'],
                        best_slot,
                        available_people,
                        token,
                        meeting.get('timezone', 'US/Mountain'),
                        start_utc=email_start_utc,
                        end_utc=email_end_utc,
                    )
                    any_success = any_success or bool(sent_ok)
                    if sent_ok:
                        print(f"Confirmation email ({milestone}) sent for slot: {best_slot}")
                    else:
                        print("Confirmation email send failed; will still attempt other channels")

                # Send via other notification methods (SMS/WhatsApp/Slack)
                if len(methods) > 1 or 'email' not in methods:
                    summary_url = url_for('meeting_summary', token=token, _external=True)
                    notification_results = notification_utils.notification_service.send_meeting_confirmation(
                        notification_preferences,
                        meeting['meeting_title'],
                        best_slot,
                        available_people,
                        summary_url
                    )
                    print(f"Notification results: {notification_results}")
                    if isinstance(notification_results, dict) and any(notification_results.values()):
                        any_success = True

                if any_success:
                    meeting_store.mark_confirmation_sent(token, best_slot, milestone)
                    print(f"Confirmation notifications marked sent for slot: {best_slot}, milestone: {milestone}")
                else:
                    print("No confirmation channels succeeded; will allow retry on next load")
            elif milestone:
                print(f"Confirmation already sent for slot: {best_slot}, milestone: {milestone}; skipping")
        except Exception as e:
            print(f"Failed to send notifications: {e}")
    
    return render_template('meeting_summary.html', 
                         meeting=meeting, 
                         responses=responses, 
                         slot_availability=slot_availability,
                         best_slot=best_slot,
                         best_slot_people=available_people,
                         no_availability_responses=no_availability_responses,
                         google_calendar_url=google_calendar_url,
                         outlook_calendar_url=outlook_calendar_url,
                         outlook_calendar_url_office=outlook_calendar_url_office)

@app.route('/connect_calendar/<token>')
def connect_calendar(token):
    """Start Google Calendar OAuth flow"""
    meeting = meeting_store.get_meeting(token)
    if not meeting:
        flash("Meeting not found", 'danger')
        return redirect(url_for('index'))
    
    try:
        authorization_url = google_calendar.get_authorization_url(token)
        return redirect(authorization_url)
    except Exception as e:
        flash("Unable to connect to Google Calendar. Please try again.", 'danger')
        return redirect(url_for('respond_meeting', token=token))

@app.route('/oauth2callback')
def oauth2callback():
    """Handle Google OAuth callback"""
    try:
        # Get authorization code and state from callback
        authorization_code = request.args.get('code')
        state = request.args.get('state')  # This should be the meeting token
        
        print(f"OAuth callback - Code: {authorization_code is not None}, State: {state}")
        print(f"Session oauth_state: {session.get('oauth_state')}")
        
        if not authorization_code or not state:
            flash("Authorization failed. Please try again.", 'danger')
            return redirect(url_for('index'))
        
        # Handle pre-create connect flow
        if state == 'precreate':
            credentials, returned_token = google_calendar.handle_oauth_callback(authorization_code, state)
            session['google_credentials_precreate'] = google_calendar.credentials_to_dict(credentials)
            # Prefill profile (name/email)
            try:
                profile = google_calendar.get_user_profile(credentials)
                if isinstance(profile, dict):
                    session['precreate_profile'] = {
                        'name': profile.get('name') or session.get('precreate_profile', {}).get('name'),
                        'email': profile.get('email') or session.get('precreate_profile', {}).get('email'),
                    }
            except Exception:
                pass
            # Make Google the active provider for this precreate session
            session['precreate_av_source'] = 'google'
            flash("Google Calendar connected successfully!", 'success')
            return redirect(url_for('create_meeting'))

        # The state parameter contains the meeting token directly for respond flow
        meeting_token = state
        # Exchange code for credentials
        credentials, returned_token = google_calendar.handle_oauth_callback(authorization_code, state)
        # Store credentials in session for this meeting
        session[f'google_credentials_{meeting_token}'] = google_calendar.credentials_to_dict(credentials)
        flash("Google Calendar connected successfully!", 'success')
        return redirect(url_for('respond_meeting', token=meeting_token))
        
    except Exception as e:
        print(f"OAuth callback error: {e}")
        flash(f"Unable to complete Google Calendar authorization: {str(e)}", 'danger')
        return redirect(url_for('index'))

@app.route('/connect_outlook/<token>')
def connect_outlook(token):
    """Start Microsoft Outlook OAuth flow"""
    meeting = meeting_store.get_meeting(token)
    if not meeting:
        flash("Meeting not found", 'danger')
        return redirect(url_for('index'))
    
    try:
        authorization_url = microsoft_calendar.get_authorization_url(token)
        return redirect(authorization_url)
    except Exception as e:
        flash("Unable to connect to Outlook calendar. Please try again.", 'danger')
        return redirect(url_for('respond_meeting', token=token))

@app.route('/msgraph/callback')
def msgraph_callback():
    """Handle Microsoft Graph OAuth callback"""
    try:
        # Get authorization code and state from callback
        authorization_code = request.args.get('code')
        state = request.args.get('state')  # This should be the meeting token
        
        print(f"Microsoft OAuth callback - Code: {authorization_code is not None}, State: {state}")
        
        if not authorization_code or not state:
            flash("Authorization failed. Please try again.", 'danger')
            return redirect(url_for('index'))
        
        if state == 'precreate':
            access_token, returned_token = microsoft_calendar.handle_oauth_callback(authorization_code, state)
            session['outlook_token_precreate'] = access_token
            # Prefill profile from Graph
            try:
                info = microsoft_calendar.get_user_info(access_token) or {}
                name = info.get('displayName')
                email = info.get('mail') or info.get('userPrincipalName')
                session['precreate_profile'] = {
                    'name': name or session.get('precreate_profile', {}).get('name'),
                    'email': email or session.get('precreate_profile', {}).get('email'),
                }
            except Exception:
                pass
            session['precreate_av_source'] = 'outlook'
            flash("Outlook calendar connected successfully!", 'success')
            return redirect(url_for('create_meeting'))

        # The state parameter contains the meeting token directly for respond flow
        meeting_token = state
        # Exchange code for access token
        access_token, returned_token = microsoft_calendar.handle_oauth_callback(authorization_code, state)
        # Store access token in session for this meeting
        session[f'outlook_token_{meeting_token}'] = access_token
        flash("Outlook calendar connected successfully!", 'success')
        return redirect(url_for('respond_meeting', token=meeting_token))
        
    except Exception as e:
        print(f"Microsoft OAuth callback error: {e}")
        flash(f"Unable to complete Outlook calendar authorization: {str(e)}", 'danger')
        return redirect(url_for('index'))

@app.route('/meeting/<token>/download-ics')
def download_ics(token):
    """Download .ics calendar file for the confirmed meeting"""
    meeting = meeting_store.get_meeting(token)
    if not meeting:
        flash("Meeting not found", 'danger')
        return redirect(url_for('index'))
    
    # Get the best time slot, fall back to the first slot if no responses yet
    best_slot, available_people = meeting_store.get_best_time_slot(token)
    selected_slot = best_slot if best_slot else (meeting['time_slots'][0] if meeting.get('time_slots') else None)
    if not selected_slot:
        flash("No meeting time available to generate an ICS file", 'warning')
        return redirect(url_for('meeting_summary', token=token))
    
    # Generate .ics file content; prefer canonical UTCs if available for the selected slot
    start_utc = None
    end_utc = None
    try:
        for item in (meeting.get('slots_meta') or []):
            if isinstance(item, dict) and item.get('display') == selected_slot:
                start_utc = item.get('start_utc')
                end_utc = item.get('end_utc')
                break
    except Exception:
        start_utc = None
        end_utc = None

    ics_content = calendar_utils.create_ics_calendar(
        meeting['meeting_title'], 
        meeting['organizer_name'], 
        selected_slot,
        timezone=meeting.get('timezone', 'US/Mountain'),
        organizer_email=meeting.get('organizer_email'),
        start_utc=start_utc,
        end_utc=end_utc,
    )
    
    if not ics_content:
        flash("Unable to generate calendar file", 'danger')
        return redirect(url_for('meeting_summary', token=token))
    
    # Return as downloadable file
    response = Response(
        ics_content,
        mimetype='text/calendar',
        headers={
            'Content-Disposition': f'attachment; filename={meeting["meeting_title"].replace(" ", "_")}.ics'
        }
    )
    return response

@app.errorhandler(404)
def page_not_found(e):
    return render_template('index.html'), 404

# --- Calendar disconnect routes ---

@app.route('/disconnect_calendar/<token>')
def disconnect_calendar(token):
    """Disconnect Google Calendar for this meeting session."""
    try:
        session.pop(f'google_credentials_{token}', None)
        flash("Disconnected Google Calendar.", 'info')
    except Exception:
        pass
    return redirect(url_for('respond_meeting', token=token))

@app.route('/disconnect_outlook/<token>')
def disconnect_outlook(token):
    """Disconnect Outlook calendar for this meeting session."""
    try:
        session.pop(f'outlook_token_{token}', None)
        flash("Disconnected Outlook calendar.", 'info')
    except Exception:
        pass
    return redirect(url_for('respond_meeting', token=token))
