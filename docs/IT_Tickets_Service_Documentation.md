# Zoho Ticket API Service

A robust Flask REST API to interact with the Zoho Desk ticketing platform for creating, fetching, and managing IT support tickets. This service manages token renewal, error handling, and supports both ticket creation and retrieval.

## Features

- **Create Tickets**: Submit new tickets to Zoho Desk
- **Fetch Ticket Details**: Retrieve complete ticket data including status, technician, and comments
- **Thread-Safe OAuth Token Management**: Automatically handles token refreshes using Zoho's refresh token flow
- **Detailed Logging**: Writes logs to both file (`zoho_api.log`) and console for traceability
- **Consistent Error Handling**: Returns actionable error messages and HTTP codes
- **Data Transformation**: Automatically converts client-friendly formats to Zoho API requirements

## Architecture Overview

### Component Design

The service follows a middleware architecture pattern:

1. **Flask Application Layer**: Handles HTTP requests, routing, and error responses
2. **Authentication Layer**: Thread-safe OAuth token management with automatic refresh
3. **Data Transformation Layer**: Converts between client API format and Zoho API format
4. **Zoho API Integration**: Interacts with Zoho Desk v3 REST API
5. **Logging Layer**: Dual logging (file + console) for production monitoring

### Key Design Decisions

#### 1. Thread-Safe Token Management
The service implements a **double-check locking pattern** for token management:

```python
def ensure_valid_token():
    if is_token_valid():  # First check (no lock)
        return True
    with _token_lock:  # Acquire lock
        if is_token_valid():  # Second check (after acquiring lock)
            return True
        return get_access_token()
```

**Why this pattern:**
- Prevents race conditions in multithreaded Flask environment
- Avoids unnecessary lock acquisition when token is valid
- Ensures only one thread refreshes the token at a time
- Other threads wait and reuse the newly refreshed token

#### 2. Token Pre-Expiry Refresh
Tokens are refreshed **5 minutes before actual expiration**:

```python
token_store["expires_at"] = datetime.now() + timedelta(seconds=expires_in - 300)
```

**Benefits:**
- Prevents mid-request token expiration
- Accounts for clock skew between servers
- Provides safety margin for token refresh failures

#### 3. Response Simplification
The `_parse_ticket_details()` function extracts essential fields from Zoho's verbose JSON response:

**Zoho response** (70+ fields) → **Simplified response** (5 key fields):
- `ticket_id`
- `status`
- `technician_assigned`
- `technician_contact_email`
- `technician_comments`

**Why:** Reduces payload size and provides client-friendly interface.

#### 4. Data Transformation for Client Convenience
The service accepts `requester_email` as a flat field and transforms it to Zoho's nested format:

**Client sends:**
```json
{"requester_email": "user@company.com", "subject": "Issue"}
```

**Service transforms to:**
```json
{"request": {"requester": {"email_id": "user@company.com"}, "subject": "Issue"}}
```

**Why:** Simplifies client implementation; encapsulates Zoho API complexity.

#### 5. Dual Logging (File + Console)
All operations logged to both:
- **File** (`zoho_api.log`): Persistent audit trail for compliance
- **Console**: Real-time monitoring and debugging

**Log format:**
```
2025-11-25 17:00:00 - __main__ - INFO - Attempting to refresh Zoho access token...
```

#### 6. Form-Encoded POST for Zoho Compatibility
Zoho Desk API requires `application/x-www-form-urlencoded` with `input_data` key containing JSON string:

```python
payload = {'input_data': json.dumps(zoho_request_wrapper)}
headers = {"Content-Type": "application/x-www-form-urlencoded"}
```

**Why:** Zoho API design quirk; JSON Content-Type is not supported for ticket creation.

## Setup and Installation

### Prerequisites
- Python 3.9+
- Registered Zoho Desk app with appropriate API credentials
- All dependencies listed in requirements.txt

### Zoho Desk App Registration

**Step 1: Create Zoho Desk Account**
1. Sign up for Zoho Desk at https://desk.zoho.com
2. Complete organization setup

**Step 2: Register API Client**
1. Navigate to Zoho API Console: https://api-console.zoho.com
2. Click "Add Client"
3. Select "Server-based Applications"
4. Fill in:
   - Client Name: Your application name
   - Homepage URL: Your application URL
   - Authorized Redirect URI: `http://localhost` (for initial setup)
5. Save and note down `CLIENT_ID` and `CLIENT_SECRET`

**Step 3: Generate Refresh Token**
1. Construct authorization URL:
```
https://accounts.zoho.com/oauth/v2/auth?scope=Desk.tickets.ALL&client_id=YOUR_CLIENT_ID&response_type=code&access_type=offline&redirect_uri=http://localhost
```
2. Visit URL in browser, authorize application
3. Copy `code` from redirect URL
4. Exchange code for refresh token:
```bash
curl -X POST https://accounts.zoho.com/oauth/v2/token \
  -d "code=YOUR_CODE" \
  -d "client_id=YOUR_CLIENT_ID" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "redirect_uri=http://localhost" \
  -d "grant_type=authorization_code"
```
5. Save `refresh_token` from response

### Configuration

Update `ZOHO_CONFIG` dictionary in `IT_Tickets.py`:

```python
ZOHO_CONFIG = {
    "CLIENT_ID": "1000.XXXXXXXXXXXXXXXX",
    "CLIENT_SECRET": "your-client-secret",
    "REFRESH_TOKEN": "1000.xxxxxxxxxxxxxxxxxxxxxxxx.xxxxxxxxxxxxxxxxxxxxxxxx",
    "ACCOUNTS_URL": "https://accounts.zoho.com",
    "API_BASE_URL": "https://support.yourdomain.com"  # Your Zoho Desk portal URL
}
```

**Configuration Parameters:**

| Parameter | Description | Example |
|-----------|-------------|---------|
| `CLIENT_ID` | Zoho OAuth Client ID | `1000.RES8HX16XVF2J5CNIWJ74KQHPCKU2O` |
| `CLIENT_SECRET` | Zoho OAuth Client Secret | `1a477e636ee5601709724e944853b49f3c0d9aa0e9` |
| `REFRESH_TOKEN` | Long-lived refresh token | `1000.7adcea1f467d20ba083238aa...` |
| `ACCOUNTS_URL` | Zoho Accounts URL | `https://accounts.zoho.com` |
| `API_BASE_URL` | Your Zoho Desk portal URL | `https://support.quatrrobss.com` |

> **Security Note:** In production, load credentials from environment variables or Azure Key Vault, not hardcoded values.

### Installation

1. **Clone the repo:**
```bash
git clone <repository-url>
cd zoho-ticket-api
```

2. **Install dependencies:**
```bash
pip install flask flask-cors requests
```

3. **Run the service:**
```bash
python IT_Tickets.py
```

Service available at: `http://localhost:8080` (or port from `PORT` environment variable)

## API Endpoints

### Base URL
`http://localhost:8080/`

### 1. Create Ticket

**Endpoint:** `POST /requests`

**Description:** Creates a new ticket in Zoho Desk.

**Request JSON:**
```json
{
  "subject": "Printer not working",
  "description": "The main office printer shows a paper jam error.",
  "requester_email": "employee@company.com"
}
```

**Request Schema:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `subject` | string | ✅ | Ticket subject/title |
| `description` | string | ✅ | Detailed description of the issue |
| `requester_email` | string | ✅ | Email of the person requesting support |

**Additional Optional Fields** (accepted and passed to Zoho):
- `priority`: e.g., `{"name": "High"}`
- `department`: e.g., `{"name": "IT Support"}`
- `category`: e.g., `{"name": "Hardware"}`
- `status`: e.g., `{"name": "Open"}`

**Implementation Details:**
- Token validity checked before API call
- `requester_email` transformed to `requester.email_id` nested format
- Request wrapped in Zoho-required format: `{"request": {...}}`
- POST data form-encoded with `input_data` key
- Zoho API returns full ticket object; service extracts ticket ID

**Success Response (201 Created):**
```json
{
  "message": "Ticket created successfully",
  "zoho_ticket_id": "123456789"
}
```

**Possible Errors:**
- `503 Service Unavailable`: Token refresh failed (check credentials)
- `400 Bad Request`: Invalid or empty JSON body
- `4xx/5xx`: Zoho API error (details in response)

### 2. Get Ticket Details

**Endpoint:** `GET /requests/{ticket_id}`

**Description:** Returns simplified details of a ticket (id, status, technician, comments).

**URL Parameter:**
- `ticket_id` (string): Zoho ticket ID. Example: `123456789`

**Implementation Details:**
- Token validity checked before API call
- Fetches full ticket details from Zoho
- Parses and simplifies response via `_parse_ticket_details()`
- Extracts technician name, email, and comments

**Success Response (200 OK):**
```json
{
  "ticket_id": "123456789",
  "status": "Open",
  "technician_assigned": "John Doe",
  "technician_contact_email": "john.doe@company.com",
  "technician_comments": "Investigating the printer issue. Will update soon."
}
```

**Response Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `ticket_id` | string | Zoho ticket ID |
| `status` | string | Current ticket status (Open, Pending, Closed, etc.) |
| `technician_assigned` | string | Assigned technician name or "Unassigned" |
| `technician_contact_email` | string | Technician email (null if unassigned) |
| `technician_comments` | string | Latest resolution comments (null if none) |

**Possible Errors:**
- `503 Service Unavailable`: Token refresh failed
- `404 Not Found`: Ticket ID doesn't exist
- `5xx`: Zoho API error

### Error Response Format
All endpoints return consistent JSON error format:

```json
{
  "error": "Error message summary",
  "details": {
    "code": "INVALID_DATA",
    "message": "Detailed Zoho API error message"
  }
}
```

## Important Implementation Notes

### Token Lifecycle

**Access Token:**
- **Lifetime:** 1 hour (3600 seconds)
- **Storage:** In-memory `token_store` dictionary
- **Refresh:** Automatic via refresh token when expired/about to expire

**Refresh Token:**
- **Lifetime:** Long-lived (typically 1-2 years, or indefinite)
- **Usage:** Generate new access tokens
- **Rotation:** Manual; update `ZOHO_CONFIG` when rotated

### Thread Safety
The service is thread-safe for concurrent requests:
- `threading.Lock()` protects token refresh operations
- Double-check locking pattern minimizes lock contention
- Flask default threading mode supported

### Logging Strategy
All operations logged with structured format:

**Success Log:**
```
2025-11-25 17:00:00 - __main__ - INFO - ✅ Ticket created successfully - ID: 123456
```

**Error Log:**
```
2025-11-25 17:00:00 - __main__ - ERROR - ❌ Exception during token refresh: HTTPError 401
```

**Log Rotation:** Not implemented; consider using `logging.handlers.RotatingFileHandler` for production.

### Data Format Transformation
Client API differs from Zoho API for developer convenience:

| Client Field | Zoho API Field |
|--------------|----------------|
| `requester_email` | `request.requester.email_id` |
| Flat JSON | Nested under `request` key |
| JSON Content-Type | Form-encoded with `input_data` |

## Troubleshooting

### Common Issues

1. **"API authentication failed" (503)**
   - **Cause:** Token refresh failed
   - **Solution:**
     - Verify `CLIENT_ID`, `CLIENT_SECRET`, `REFRESH_TOKEN` are correct
     - Check Zoho API Console for client status
     - Ensure refresh token hasn't been revoked
     - Check `zoho_api.log` for detailed error

2. **"Invalid or empty JSON body provided" (400)**
   - **Cause:** Malformed request body
   - **Solution:**
     - Ensure `Content-Type: application/json` header
     - Validate JSON syntax
     - Include required fields: `subject`, `description`, `requester_email`

3. **Token refresh returns "invalid_client"**
   - **Cause:** Client credentials incorrect or client revoked
   - **Solution:**
     - Verify `CLIENT_ID` and `CLIENT_SECRET` match Zoho console
     - Check client app status in Zoho API Console
     - Regenerate credentials if needed

4. **Ticket not found (404)**
   - **Cause:** Ticket ID doesn't exist or deleted
   - **Solution:**
     - Verify ticket ID from Zoho Desk portal
     - Check if ticket was deleted
     - Ensure using numeric ticket ID (not request number)

5. **Rate limit errors from Zoho**
   - **Cause:** Exceeded Zoho API rate limits
   - **Solution:**
     - Zoho limits: 2000 requests/day (varies by plan)
     - Implement request throttling
     - Upgrade Zoho Desk plan if needed

## Security Considerations

### Credential Management
- **Never commit credentials to version control**
- Use environment variables for `CLIENT_SECRET` and `REFRESH_TOKEN`
- Rotate credentials periodically (every 12-24 months)
- Monitor Zoho API Console for unauthorized access

### Token Security
- Access tokens stored in-memory only (not persisted)
- Tokens never logged or exposed in API responses
- HTTPS required for production deployments

### Input Validation
- All requests validated for required fields
- Pydantic can be added for stricter validation
- No SQL injection risk (REST API, not database)

### Network Security
- CORS enabled (configure for production)
- All Zoho API communication over HTTPS
- Consider API gateway/rate limiting for production

### Refresh Token Rotation

**When to Rotate:**
- Security best practice: Every 12-24 months
- If credentials compromised/leaked
- When changing Zoho Desk organization

**Rotation Process:**
1. Generate new refresh token via Zoho OAuth flow (see setup section)
2. Update `ZOHO_CONFIG["REFRESH_TOKEN"]`
3. Restart application
4. Test ticket creation
5. Revoke old refresh token in Zoho console

## Detailed Logging

### Log File Location
`zoho_api.log` in application directory

### Log Format
```
%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

### Log Levels
- **INFO**: Normal operations, token refresh, ticket operations
- **ERROR**: API failures, authentication errors, HTTP errors
- **CRITICAL**: Startup failures (e.g., initial token acquisition failed)

### Sample Logs
**Ticket Creation:**
```
2025-11-25 17:00:00 - __main__ - INFO - Received POST request to create a new ticket.
2025-11-25 17:00:01 - __main__ - INFO - ✅ Ticket created successfully - ID: 987654321
```

**Token Refresh:**
```
2025-11-25 17:15:00 - __main__ - INFO - Attempting to refresh Zoho access token...
2025-11-25 17:15:01 - __main__ - INFO - ✅ Successfully refreshed Zoho access token.
```

**Error:**
```
2025-11-25 17:20:00 - __main__ - ERROR - HTTP Error fetching ticket 123456: 404 Not Found
```

## Performance Considerations

### Response Times
- **Token refresh:** ~1-2 seconds (only when needed)
- **Ticket creation:** ~2-3 seconds (Zoho API latency)
- **Ticket retrieval:** ~1-2 seconds

### Scalability
- In-memory token store (not suitable for multi-instance deployments)
- For horizontal scaling, use Redis/database for token storage
- Stateless design otherwise

### Optimization Opportunities
- Implement caching for frequently accessed tickets
- Batch ticket operations when possible
- Use Zoho webhooks for real-time updates instead of polling

## Support

For technical support:
1. Review `zoho_api.log` for detailed error traces
2. Check Zoho API Console for client app status
3. Verify refresh token validity
4. Consult Zoho Desk API documentation for error codes
5. Test with Zoho API sandbox environment

**Useful Resources:**
- [Zoho Desk API Documentation](https://desk.zoho.com/support/APIDocument.do)
- [Zoho OAuth2 Guide](https://www.zoho.com/desk/developer-guide/apiv3/oauth-setup.html)
- [Zoho API Console](https://api-console.zoho.com)

---

**Service Version**: 1.0  
**Last Updated**: November 2025  
**Supported API**: Zoho Desk v3  
**Python Version**: 3.9+
