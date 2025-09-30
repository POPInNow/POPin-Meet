# Schedule Coordinator

## Overview

Schedule Coordinator is a web-based meeting scheduling application that allows organizers to create meeting polls with multiple time slot options and collect availability responses from participants. The system helps find the optimal meeting time by aggregating participant availability and identifying the time slot with the highest consensus.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Template Engine**: Jinja2 templates with Flask for server-side rendering
- **UI Framework**: Bootstrap 5 with dark theme for responsive design
- **Component Structure**: Base template with extended child templates for different pages
- **Styling**: FontAwesome icons and Bootstrap components for consistent UI

### Backend Architecture
- **Web Framework**: Flask with Python for lightweight web application development
- **Application Structure**: Modular design with separate files for routes, models, and main application
- **Session Management**: Flask sessions with configurable secret key for security
- **Routing**: RESTful URL patterns for meeting creation, response collection, and summary views

### Data Storage Solution
- **Storage Type**: In-memory data storage using Python dictionaries and collections
- **Data Models**: 
  - MeetingStore class managing meetings and responses
  - Meeting data includes organizer info, title, time slots, and creation timestamp
  - Response data tracks participant availability with timestamps
- **Data Persistence**: No persistent storage - data is lost on application restart
- **Performance Considerations**: Suitable for development and small-scale usage

### Core Features
- **Meeting Creation**: Organizers can create meetings with 2-3 time slot options
- **Response Collection**: Participants vote on their availability for proposed time slots
- **Consensus Finding**: Algorithm to identify time slot with highest participant availability
- **Summary Dashboard**: Real-time view of responses and optimal scheduling recommendations
- **Link Sharing**: Unique URLs for each meeting to share with participants

### Security and Validation
- **Input Validation**: Server-side validation for required fields and data constraints
- **Session Security**: Configurable session secret with environment variable support
- **Error Handling**: Flash messages for user feedback and form validation errors

### URL Structure
- `/` - Landing page with application overview
- `/create` - Meeting creation form
- `/meeting/<id>/created` - Confirmation page with shareable link
- `/meeting/<id>/respond` - Participant response form
- `/meeting/<id>/summary` - Results and availability summary

## External Dependencies

### Frontend Dependencies
- **Bootstrap 5**: CSS framework for responsive design and UI components
- **FontAwesome 6**: Icon library for visual elements
- **Replit Bootstrap Theme**: Dark theme customization for Replit environment

### Backend Dependencies
- **Flask**: Web framework for Python applications
- **UUID**: Python standard library for generating unique meeting identifiers
- **Datetime**: Python standard library for timestamp management
- **Collections**: Python standard library for defaultdict data structures
- **OS**: Environment variable access for configuration management

### Development Environment
- **Logging**: Python logging module configured for debug-level output
- **Development Server**: Flask development server with debug mode enabled
- **Host Configuration**: Application configured to run on all interfaces (0.0.0.0:5000)

Note: The application currently uses in-memory storage and would benefit from a persistent database solution like PostgreSQL for production deployment.