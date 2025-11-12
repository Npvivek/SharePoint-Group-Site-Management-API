# Zoho Ticket API Service

A robust Flask REST API to interact with the Zoho Desk ticketing platform for creating, fetching, and managing IT support tickets. This service manages token renewal, error handling, and supports both ticket creation and retrieval.

## Features

- **Create Tickets**: Submit new tickets to Zoho Desk
- **Fetch Ticket Details**: Retrieve complete ticket data including status, technician, and comments
- **Thread-safe OAuth Token Management**: Automatically handles token refreshes using Zoho's refresh token flow
- **Detailed Logging**: Writes logs to both file and console for traceability
- **Consistent Error Handling**: Returns actionable error messages and HTTP codes

## Setup and Installation

### Prerequisites
- Python 3.9+
- Registered Zoho Desk app with appropriate API credentials
- All dependencies listed in requirements.txt

### Zoho API Credentials (Environment variables or config section)
- CLIENT_ID
- CLIENT_SECRET
- REFRESH_TOKEN
- ACCOUNTS_URL (e.g. https://accounts.zoho.com)
- API_BASE_URL (e.g. https://support.yourdomain.com)

### Installation
1. Clone the repo and run:
2. `pip install -r requirements.txt`
3. Configure your Zoho Desk API credentials in environment or in code

## API Endpoints

### Base URL
`http://localhost:7000/`

### 1. Create Ticket
- `POST /requests`
- Creates a new ticket

**Request JSON:**
```json
{
  "subject": "Printer not working",
  "description": "The main office printer shows a paper jam error.",
  "requesteremail": "employee@company.com"
}
```
*Zoho requires requester email as "email" key internally.

**Response:**
```json
{
  "message": "Ticket created successfully",
  "zohoticketid": "123456789"
}
```

### 2. Get Ticket Details
- `GET /requests/{ticket_id}`
- Returns simplified details of ticket (id, status, technician, comments)

**Example:**
```bash
curl -X GET http://localhost:7000/requests/123456789
```

### Error Response
All endpoints:
- Consistent JSON error format with HTTP code for failures (e.g. auth, network, invalid input)

## Examples

### Create Ticket
```bash
curl -X POST http://localhost:7000/requests \
  -H "Content-Type: application/json" \
  -d '{"subject": "Network down", "description": "Cannot access internet.", "requesteremail": "ituser@domain.com"}'
```

### Get Ticket
```bash
curl -X GET http://localhost:7000/requests/123456789
```

## Detailed Logging
- All actions logged to `zohoapi.log` and to console with timestamps, request IDs
- Errors include exact failure reason (auth, HTTP error, Zoho API message)

## Security Considerations
- Store Zoho API credentials securely in environment variables
- Refresh tokens and access tokens should not be exposed or hard-coded

### Token Rotation
- Zoho Desk access tokens expire every hour; this service auto-renews via refresh token
- Refresh tokens may expire/rotate—rotate in Zoho developer console and update the service config as per Zoho's best practices
- Consider rotating refresh tokens every 1–2 years as part of security policy

## Troubleshooting
- Auth failures: Verify that CLIENT_ID, CLIENT_SECRET, and REFRESH_TOKEN are correct and active; check expiration
- API/Network errors: Inspect logs for detailed exception messages (file + console)
- Ticket not found: Verify ticket ID or if it is deleted in Zoho Desk

## Support
- Review logs and exception traces for troubleshooting
- For persistent auth errors, reissue refresh token in Zoho developer console and update service config

---
**Service Version**: 1.0  
**Last Updated**: Nov 2025  
**Supported API**: Zoho Desk v3
