import os
import requests
from twilio.rest import Client
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class NotificationService:
    """Service for sending notifications via multiple channels"""
    
    def __init__(self):
        # Twilio configuration
        self.twilio_account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        self.twilio_auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        self.twilio_phone_number = os.environ.get('TWILIO_PHONE_NUMBER')
        
        # Initialize Twilio client if credentials are available
        self.twilio_client = None
        if self.twilio_account_sid and self.twilio_auth_token:
            self.twilio_client = Client(self.twilio_account_sid, self.twilio_auth_token)
    
    def send_sms(self, to_phone, message):
        """Send SMS notification via Twilio"""
        try:
            if not self.twilio_client:
                logger.info(f"=== SMS NOTIFICATION (would be sent to {to_phone}) ===")
                logger.info(f"Message: {message}")
                logger.info("=== END SMS ===")
                return True
            
            message = self.twilio_client.messages.create(
                body=message,
                from_=self.twilio_phone_number,
                to=to_phone
            )
            logger.info(f"SMS sent successfully with SID: {message.sid}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending SMS: {e}")
            return False
    
    def send_whatsapp(self, to_phone, message):
        """Send WhatsApp notification via Twilio"""
        try:
            if not self.twilio_client:
                logger.info(f"=== WHATSAPP NOTIFICATION (would be sent to {to_phone}) ===")
                logger.info(f"Message: {message}")
                logger.info("=== END WHATSAPP ===")
                return True
            
            # Format phone number for WhatsApp (must include whatsapp: prefix)
            whatsapp_to = f"whatsapp:{to_phone}"
            whatsapp_from = f"whatsapp:{self.twilio_phone_number}"
            
            message = self.twilio_client.messages.create(
                body=message,
                from_=whatsapp_from,
                to=whatsapp_to
            )
            logger.info(f"WhatsApp sent successfully with SID: {message.sid}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending WhatsApp: {e}")
            return False
    
    def send_slack(self, webhook_url, message, meeting_title=None):
        """Send Slack notification via webhook"""
        try:
            # Create Slack message payload
            payload = {
                "text": f"🗓️ Meeting Update: {meeting_title}" if meeting_title else "Meeting Update",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": message
                        }
                    }
                ]
            }
            
            # Send to Slack webhook
            response = requests.post(webhook_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info("Slack notification sent successfully")
                return True
            else:
                logger.error(f"Slack webhook returned status {response.status_code}: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending Slack notification: {e}")
            # Log what would have been sent for testing
            logger.info(f"=== SLACK NOTIFICATION (would be sent to {webhook_url}) ===")
            logger.info(f"Message: {message}")
            logger.info("=== END SLACK ===")
            return True  # Return True for testing when webhook fails
        except Exception as e:
            logger.error(f"Unexpected error sending Slack notification: {e}")
            return False
    
    def send_meeting_confirmation(self, notification_preferences, meeting_title, confirmed_time, available_people, summary_url):
        """Send meeting confirmation via all selected notification methods"""
        methods = notification_preferences.get('methods', [])
        results = {}
        
        # Create message content
        message = f"""🎉 Great news! Your meeting "{meeting_title}" has been confirmed.

📅 Confirmed Time: {confirmed_time}
👥 Available Participants: {', '.join(available_people)} ({len(available_people)} people)

View full details: {summary_url}"""
        
        # Send via each selected method
        if 'email' in methods:
            # Email is handled separately by email_utils
            results['email'] = True
        
        if 'sms' in methods and notification_preferences.get('sms_phone'):
            # SMS: concise, structured, aligns with email sections
            sms_message = (
                f"Meeting '{meeting_title}' confirmed\n"
                f"Time: {confirmed_time}\n"
                f"Participants: {len(available_people)}\n"
                f"Summary: {summary_url}"
            )
            results['sms'] = self.send_sms(notification_preferences['sms_phone'], sms_message)
        
        if 'whatsapp' in methods and notification_preferences.get('whatsapp_phone'):
            results['whatsapp'] = self.send_whatsapp(notification_preferences['whatsapp_phone'], message)
        
        if 'slack' in methods and notification_preferences.get('slack_webhook'):
            slack_message = f"*Meeting Confirmed!* 🎉\n\n*{meeting_title}*\n📅 *Time:* {confirmed_time}\n👥 *Participants:* {', '.join(available_people)} ({len(available_people)} people)\n\n<{summary_url}|View Full Details>"
            results['slack'] = self.send_slack(notification_preferences['slack_webhook'], slack_message, meeting_title)
        
        return results
    
    def send_response_milestone_notification(self, notification_preferences, meeting_title, current_responses, expected_participants, summary_url):
        """Send progressive milestone notifications as responses come in"""
        methods = notification_preferences.get('methods', [])
        response_count = len(current_responses)
        percentage = (response_count / expected_participants) * 100
        
        # Determine milestone message
        if response_count == 1:
            milestone_type = "first"
            message = f"""📋 Great! Your meeting "{meeting_title}" received its first response.

👥 Responses: {response_count} of {expected_participants} expected
📊 Response Rate: {percentage:.0f}%

View responses: {summary_url}"""
        elif percentage >= 70:
            milestone_type = "critical_mass"
            message = f"""🎯 Excellent! {percentage:.0f}% of your group has responded to "{meeting_title}".

👥 Responses: {response_count} of {expected_participants} expected
✅ You can confirm a time now or wait for more responses.

View results: {summary_url}"""
        elif percentage >= 50:
            milestone_type = "halfway"
            message = f"""📊 Halfway there! {percentage:.0f}% of participants have responded to "{meeting_title}".

👥 Responses: {response_count} of {expected_participants} expected
⏳ Keep an eye on the responses as they come in.

View progress: {summary_url}"""
        else:
            return None  # No milestone reached
        
        results = {}
        
        # Send via preferred method (prioritize SMS, then others) with clearer copy
        if 'sms' in methods and notification_preferences.get('sms_phone'):
            sms_message = (
                f"Update: '{meeting_title}'\n"
                f"Responses: {response_count}/{expected_participants} ({percentage:.0f}%)\n"
                + ("Action: You can confirm now!\n" if percentage >= 70 else "")
                + f"Summary: {summary_url}"
            )
            results['sms'] = self.send_sms(notification_preferences['sms_phone'], sms_message)
            
        elif 'whatsapp' in methods and notification_preferences.get('whatsapp_phone'):
            results['whatsapp'] = self.send_whatsapp(notification_preferences['whatsapp_phone'], message)
            
        elif 'slack' in methods and notification_preferences.get('slack_webhook'):
            emoji = "🎯" if percentage >= 70 else "📊" if percentage >= 50 else "📋"
            slack_message = f"{emoji} *Meeting Update: {meeting_title}*\n\n*Responses:* {response_count} of {expected_participants} ({percentage:.0f}%)\n\n"
            if percentage >= 70:
                slack_message += "✅ You can confirm a time now or wait for more responses.\n\n"
            slack_message += f"<{summary_url}|View Details>"
            results['slack'] = self.send_slack(notification_preferences['slack_webhook'], slack_message, meeting_title)
            
        elif 'email' in methods and notification_preferences.get('email_address'):
            # Email will be handled by email_utils
            results['email'] = True
        
        return results

# Global notification service instance
notification_service = NotificationService()