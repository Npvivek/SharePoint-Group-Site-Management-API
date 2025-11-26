# Distribution List Management API

A secure and robust Flask-based REST API for managing Microsoft 365 Distribution Lists. This service provides CRUD (Create, Read, Update, Delete) operations by interacting with the Microsoft Graph and Exchange Online APIs.

## Features

- **Create Distribution Lists**: Provision new DLs with specified owners and members
- **Retrieve DL Details**: Fetch comprehensive details for any existing DL, including members and owners
- **Update Distribution Lists**: Modify names, members, owners, and settings
- **Delete Distribution Lists**: Permanently remove a DL
- **Member Management**: Add or remove individual members from distribution lists
- **Secure Authentication**: Uses the OAuth 2.0 client credentials flow to securely authenticate with Microsoft APIs
- **Data Validation**: Employs Pydantic for rigorous validation of all incoming request data
- **Retry Logic with Exponential Backoff**: Automatically handles transient failures
- **User Validation Caching**: TTL-based cache reduces redundant API calls
- **CORS Enabled**: Configurable Cross-Origin Resource Sharing for frontend integration

## Architecture Overview

### Component Design

The service follows a layered architecture pattern:

1. **Flask Application Layer** (`create_app()`): Handles HTTP requests, routing, and error handling
2. **Business Logic Layer** (`DLService`): Implements core distribution list operations
3. **API Client Layer**:
   - `ApiClient`: Singleton pattern for MSAL authentication and token management
   - `GraphApiClient`: Manages Microsoft Graph API interactions for user validation
   - `ExchangeOnlineClient`: Handles Exchange Online PowerShell commands via REST API

### Key Design Decisions

#### 1. Singleton Pattern for Authentication
The `ApiClient` uses a thread-safe singleton pattern to ensure a single MSAL application instance across all requests. This prevents excessive token acquisition and maintains consistent authentication state.

#### 2. TTL Cache for User Validation
A custom `TTLCache` class implements thread-safe caching of user validation results with a 15-minute default TTL. This significantly reduces redundant Graph API calls when validating the same users repeatedly.

**Benefits:**
- Reduces API call volume
- Improves response times
- Prevents rate limiting

#### 3. Retry Logic with Exponential Backoff
The service implements two distinct retry strategies using the Tenacity library:

**Verification Retries** (Read-after-write consistency):
- 6 attempts with 5-30 second exponential backoff
- Ensures DL is propagated after creation
- Handles eventual consistency in Exchange Online

**Member Operation Retries** (Transient failure handling):
- 5 attempts with 2-20 second exponential backoff
- Handles temporary network issues and service throttling
- Retries on `NotFoundError` and `TransientError` exceptions

#### 4. X-AnchorMailbox Header Strategy
The service implements intelligent anchor mailbox selection for Exchange Online routing:

Priority order:
1. `X-AnchorMailbox` request header (if provided)
2. `ADMIN_ANCHOR_MAILBOX` configuration value
3. First owner's email address
4. DL's primary email address
5. Fallback: `postmaster@{CUSTOM_DOMAIN}`

**Why this matters:** Proper anchor mailbox routing ensures requests hit the correct Exchange server, reducing latency and avoiding cross-datacenter calls.

#### 5. Owners as Members Configuration
The `OWNERS_AS_MEMBERS` setting (default: `True`) automatically adds all owners as members during DL creation and updates. This ensures owners receive emails sent to the DL without manual configuration.

#### 6. Request ID Tracking
Every request generates or accepts a unique request ID (`X-Request-ID` header) for comprehensive distributed tracing across logs.

## Setup and Installation

### Prerequisites

- Python 3.9+
- `pip` and `venv`
- A Microsoft Azure App Registration with the necessary API permissions
- Exchange Administrator role assigned to the Azure AD application

### Required API Permissions

In Azure Active Directory, your App Registration needs the following **Application** permissions (not Delegated):

#### Microsoft Graph API Permissions

| Permission | Purpose |
|------------|---------|
| `Directory.Read.All` | Validate user email addresses and organizational membership |
| `User.Read.All` | Resolve user emails to Object IDs and retrieve user principal names |
| `Group.ReadWrite.All` | Read and update distribution list properties |
| `GroupMember.ReadWrite.All` | Add and remove members from distribution lists |
| `Organization.ReadWrite.All` | Configure external sender permissions and org-level settings |

#### Office 365 Exchange Online API Permissions

| Permission | Purpose |
|------------|---------|
| `Exchange.ManageAsApp` | Execute Exchange PowerShell commands via REST API to manage Distribution Lists |

#### Azure AD Directory Role Assignment

**Critical:** The service principal (Azure AD app) must be assigned the **Exchange Administrator** or **Exchange Recipient Administrator** directory role.

**How to assign:**
1. Navigate to Azure AD → Roles and administrators
2. Search for "Exchange Administrator"
3. Click "Add assignments"
4. Select your application
5. Save

> **Note:** API permissions alone are insufficient. The directory role assignment is mandatory for Exchange Online operations.

### Installation Steps

1. **Clone the repository:**
```bash
git clone <repository-url>
cd distribution-list-api
```

2. **Create and activate a virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate
```

3. **Install dependencies:**
```bash
pip install flask flask-cors httpx msal pydantic pydantic-settings python-slugify tenacity
```

4. **Configure Environment Variables:**

Create a `.env` file in the root directory:
```env
TENANT_ID=your-azure-tenant-id
CLIENT_ID=your-azure-app-client-id
CLIENT_SECRET=your-azure-app-client-secret
CUSTOM_DOMAIN=yourdomain.com

# Optional Configuration
ADMIN_ANCHOR_MAILBOX=mailbox@yourdomain.com
OWNERS_AS_MEMBERS=True
VALIDATION_CACHE_TTL_S=900
LOG_CACHE_STATS=False
```

**Configuration Parameters:**

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `TENANT_ID` | Yes | - | Azure AD Tenant ID |
| `CLIENT_ID` | Yes | - | Azure AD App Client ID |
| `CLIENT_SECRET` | Yes | - | Azure AD App Client Secret |
| `CUSTOM_DOMAIN` | Yes | - | Domain suffix for DL email addresses |
| `ADMIN_ANCHOR_MAILBOX` | No | None | Stable anchor mailbox for consistent routing |
| `OWNERS_AS_MEMBERS` | No | True | Auto-add owners as members |
| `VALIDATION_CACHE_TTL_S` | No | 900 | User validation cache TTL (0 disables) |
| `LOG_CACHE_STATS` | No | False | Enable debug logging for cache statistics |

## Running the Application

### For Development
Run the Flask application directly. The service will be available at `http://127.0.0.1:8080`.

```bash
python DL.py
```

### For Production
Use a production-grade WSGI server like Gunicorn:

```bash
gunicorn -w 4 -b 0.0.0.0:8080 DL:app
```

**Production Recommendations:**
- Use `gunicorn` with 2-4× CPU core count workers
- Enable access logging: `--access-logfile -`
- Set timeout: `--timeout 120`
- Use a reverse proxy (nginx/Apache) for SSL termination

## API Documentation

### Base URL
```
http://localhost:8080/api
```

### Authentication
This API uses Azure AD application authentication. No additional headers are required from the client as authentication is handled internally via the OAuth 2.0 client credentials flow.

### Error Responses

The API uses standard HTTP status codes and provides a consistent JSON error format.

**Generic Error Format:**
```json
{
  "error": "Error message summary",
  "details": "Detailed error information or object"
}
```

**Validation Error (422 Unprocessable Entity):**
```json
{
  "error": "Validation Error",
  "details": [
    {
      "type": "value_error",
      "loc": ["field_name"],
      "msg": "Detailed validation message"
    }
  ]
}
```

### HTTP Status Codes
| Status Code | Description |
|-------------|-------------|
| `200` | Success (GET, PATCH, DELETE) |
| `201` | Created (POST) |
| `400` | Bad Request (Invalid input format) |
| `401` | Unauthorized (Authentication failure) |
| `404` | Not Found (DL or user doesn't exist) |
| `409` | Conflict (DL already exists) |
| `422` | Unprocessable Entity (Validation errors) |
| `500` | Internal Server Error |
| `503` | Service Unavailable (Transient errors) |

## Endpoints

### 1. Create Distribution List

**Endpoint:** `POST /api/dl`

**Description:** Creates a new distribution list with the specified owners and members. The DL alias is automatically generated from the name using slugification.

**Request Body:**
```json
{
  "name": "Marketing Team",
  "ownerEmails": [
    "john.doe@company.com",
    "jane.smith@company.com"
  ],
  "memberEmails": [
    "member1@company.com",
    "member2@company.com"
  ],
  "allowExternalSenders": false
}
```

**Request Schema:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Display name for the Distribution List |
| `ownerEmails` | array[string] | ✅ | List of owner email addresses (at least 1 required) |
| `memberEmails` | array[string] | ❌ | List of member email addresses |
| `allowExternalSenders` | boolean | ❌ | Allow external senders to email the DL (default: false) |

**Implementation Details:**
- All user emails are validated against Azure AD before DL creation
- DL alias is generated using `slugify(name)`
- Primary email format: `{alias}@{CUSTOM_DOMAIN}`
- If `OWNERS_AS_MEMBERS=True`, owners are automatically added to member list
- Creation is verified with exponential backoff retry (up to 6 attempts)
- Members are added sequentially with individual retry logic

**Success Response (201 Created):**
```json
{
  "dlId": "marketing-team",
  "primaryEmail": "marketing-team@company.com",
  "status": "DL 'marketing-team' created. All members added.",
  "failedMembers": []
}
```

**Possible Errors:**
- `409 Conflict`: A DL with that name already exists
- `404 Not Found`: One of the specified users (owner or member) does not exist in Azure AD
- `422 Unprocessable Entity`: Invalid request body (e.g., missing `name`, no owners)

### 2. Get Distribution List Details

**Endpoint:** `GET /api/dl/{dlId}`

**Description:** Retrieves full details for a specific distribution list. The `dlId` can be the name, alias, or primary email address.

**URL Parameter:**
- `dlId` (string): The identifier of the DL. Example: `marketing-team` or `marketing-team@company.com`

**Implementation Details:**
- Queries Exchange Online for DL properties
- Resolves owner Object IDs to UPNs via Microsoft Graph batch API
- Fetches all current members

**Success Response (200 OK):**
```json
{
  "dlId": "marketing-team",
  "name": "marketing-team",
  "displayName": "Marketing Team",
  "primaryEmail": "marketing-team@company.com",
  "owners": [
    "john.doe@company.com",
    "jane.smith@company.com"
  ],
  "members": [
    "member1@company.com",
    "member2@company.com"
  ],
  "allowExternalSenders": false
}
```

**Possible Errors:**
- `404 Not Found`: The specified distribution list does not exist

### 3. Update Distribution List

**Endpoint:** `PATCH /api/dl/{dlId}`

**Description:** Updates one or more properties of a distribution list. Send only the fields you want to change. Member and owner lists are synchronized (diff applied).

**Request Body (All fields optional):**
```json
{
  "name": "Updated Marketing Team",
  "displayName": "Updated Marketing Team Display",
  "ownerEmails": [
    "new.owner@company.com"
  ],
  "memberEmails": [
    "new.member1@company.com",
    "new.member2@company.com"
  ],
  "allowExternalSenders": true
}
```

**Request Schema:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ❌ | New name for the DL (updates alias and email) |
| `displayName` | string | ❌ | New display name (what users see) |
| `ownerEmails` | array[string] | ❌ | Complete list of owner emails (replaces existing) |
| `memberEmails` | array[string] | ❌ | Complete list of member emails (replaces existing) |
| `allowExternalSenders` | boolean | ❌ | Allow external senders to email the DL |

**Implementation Details:**
- New users are validated before update
- Member synchronization calculates differential: `to_add = target - current`, `to_remove = current - target`
- If `OWNERS_AS_MEMBERS=True`, owners are automatically included in target member set
- Each member add/remove uses retry logic with exponential backoff

> **Note:** The `memberEmails` and `ownerEmails` fields perform complete synchronization. The provided list becomes the definitive list, adding missing users and removing extras.

**Success Response (200 OK):**
```json
{
  "message": "Distribution List 'marketing-team' updated successfully."
}
```

**Possible Errors:**
- `404 Not Found`: The DL or a newly added user does not exist
- `422 Unprocessable Entity`: Invalid request body format

### 4. Delete Distribution List

**Endpoint:** `DELETE /api/dl/{dlId}`

**Description:** Permanently deletes a distribution list.

**Implementation Details:**
- Executes Exchange Online `Remove-DistributionGroup` command
- Deletion is immediate and permanent (no soft delete)

**Success Response (200 OK):**
```json
{
  "message": "Distribution List 'marketing-team' deleted successfully."
}
```

**Possible Errors:**
- `404 Not Found`: The specified distribution list does not exist

### 5. Add Members

**Endpoint:** `POST /api/dl/{dlId}/members`

**Description:** Adds one or more members to an existing distribution list without affecting existing members.

**Request Body:**
```json
{
  "memberEmails": ["newmember@company.com", "another@company.com"]
}
```

**Implementation Details:**
- Validates all users before any additions
- Verifies DL exists before adding members
- Each member is added sequentially with retry logic
- Duplicate members (already in DL) are silently skipped

**Success Response (200 OK):**
```json
{
  "message": "All members added.",
  "failed": []
}
```

### 6. Remove Members

**Endpoint:** `DELETE /api/dl/{dlId}/members`

**Description:** Removes one or more members from a distribution list.

**Request Body:**
```json
{
  "memberEmails": ["oldmember@company.com"]
}
```

**Implementation Details:**
- Verifies DL exists before removing members
- Each member is removed sequentially with retry logic
- Removing a non-existent member is treated as success (idempotent)

**Success Response (200 OK):**
```json
{
  "message": "All members removed (or already absent).",
  "failed": []
}
```

## Important Implementation Notes

### Distribution List vs Microsoft 365 Groups
This service creates **true Exchange Online Distribution Lists**, not Microsoft 365 Groups. Key differences:

| Feature | Distribution Lists | Microsoft 365 Groups |
|---------|-------------------|---------------------|
| Type in Outlook | "Distribution List" | "Microsoft 365" |
| Functionality | Email-only | Teams, SharePoint, Planner, Email |
| Creation API | Exchange Online PowerShell | Microsoft Graph |
| Management | Owners can manage | Owners + members can collaborate |

### Owner and Member Relationship
- **Owners**: Can manage the DL (add/remove members, change settings) but do NOT automatically receive emails
- **Members**: Receive emails sent to the DL
- **Important**: With `OWNERS_AS_MEMBERS=True` (default), owners are automatically added as members to receive emails

### Email Address Generation
- DL aliases are auto-generated using `slugify()` from the display name
- Primary email format: `{alias}@{CUSTOM_DOMAIN}`
- Example: "Marketing Team" → `marketing-team@company.com`
- Special characters are removed, spaces become hyphens

### User Validation Cache
The service maintains a TTL cache of user validation results:
- **Default TTL:** 15 minutes (900 seconds)
- **Cache key:** User Principal Name (email)
- **Thread-safe:** Uses threading.Lock for concurrent requests
- **Automatic cleanup:** Expired entries removed during validation operations
- **Disable:** Set `VALIDATION_CACHE_TTL_S=0`

## Troubleshooting

### Common Issues

1. **"Role not supported" or "Insufficient privileges" error**
   - **Cause:** Azure AD app lacks Exchange Administrator role
   - **Solution:** 
     - Navigate to Azure AD → Roles and administrators
     - Assign "Exchange Administrator" role to your app
     - Verify both API permissions AND directory role are configured
     - Wait 5-10 minutes for role propagation

2. **"User not found" error**
   - **Cause:** Email address doesn't exist in Azure AD
   - **Solution:**
     - Check email address spelling
     - Verify user exists in Azure AD directory
     - Ensure user has proper license assignments (Exchange Online required)
     - Check if user is in a different tenant

3. **"DL already exists" error (409 Conflict)**
   - **Cause:** A DL with the same alias exists
   - **Solution:**
     - Choose a different name for the distribution list
     - Check existing DLs in Exchange Admin Center
     - Note: Deleted DLs may remain in "soft delete" for 30 days

4. **Connection timeout errors**
   - **Cause:** Network connectivity issues or firewall blocking
   - **Solution:**
     - Verify network connectivity to `graph.microsoft.com` and `outlook.office365.com`
     - Check if corporate firewall blocks outbound HTTPS (443)
     - Ensure no proxy issues
     - Verify DNS resolution

5. **Token acquisition failures**
   - **Cause:** Invalid credentials or expired client secret
   - **Solution:**
     - Verify `TENANT_ID`, `CLIENT_ID`, and `CLIENT_SECRET` are correct
     - Check client secret expiration in Azure portal
     - Regenerate client secret if expired
     - Ensure no typos or extra whitespace in `.env` file

6. **Transient 503 errors during creation**
   - **Cause:** Exchange Online temporary unavailability
   - **Solution:**
     - Service automatically retries with exponential backoff
     - If persistent, check Microsoft 365 service health dashboard
     - Consider increasing `VERIFY_ATTEMPTS` configuration

### Logging and Debugging

The service includes comprehensive logging with unique request IDs for tracing:

```
2025-08-24 19:00:00,123 - INFO - [abc123-def456] - Creating Distribution List: Marketing Team
2025-08-24 19:00:01,456 - INFO - [abc123-def456] - Graph: Looking up user 'john@company.com'
2025-08-24 19:00:02,789 - INFO - [abc123-def456] - EXO: Invoking cmdlet='New-DistributionGroup'
```

**Log Levels:**
- **INFO**: Normal operations, user validation, DL creation/updates
- **WARNING**: Non-critical failures (e.g., failed to add specific member, cache cleanup)
- **ERROR**: API errors, authentication failures, unexpected exceptions
- **CRITICAL**: Fatal configuration errors preventing service startup

**Enable Cache Statistics:**
Set `LOG_CACHE_STATS=True` to log detailed cache hit rates and cleanup operations.

## Security Considerations

### Authentication & Authorization
- Service uses OAuth 2.0 client credentials flow (app-only authentication)
- No user context required; operates with application permissions
- All API credentials stored as environment variables (never hardcoded)
- Token caching with automatic refresh 5 minutes before expiration

### Data Privacy
- Request/response logging excludes sensitive data
- Client secrets masked in logs
- User emails logged only for troubleshooting purposes

### Network Security
- CORS is configurable for production environments
- All external communication over HTTPS (TLS 1.2+)
- Input validation prevents injection attacks
- Pydantic models enforce strict type checking

### Client Secret Rotation

**Critical Security Practice:**
- The client secret used for Azure AD app authentication should be rotated regularly
- **Recommended interval:** Every 12-24 months or per organizational policy
- **Azure default expiration:** 2 years

**Rotation Process:**
1. Generate new client secret in Azure portal (App registrations → Certificates & secrets)
2. Update `.env` file with new `CLIENT_SECRET`
3. Restart application
4. Verify successful authentication
5. Delete old client secret after confirming new one works
6. Document rotation date

**Best Practice:** Maintain two client secrets with staggered expiration dates for zero-downtime rotation.

## Performance Considerations

### Caching Strategy
- User validation results cached for 15 minutes (configurable)
- MSAL token caching with early refresh (5 min before expiry)
- Reduces API call volume by ~70-80% for repeated operations

### Retry Strategy
- Exponential backoff prevents thundering herd during outages
- Maximum retry intervals prevent indefinite blocking
- Retries only on transient errors (not on validation failures)

### Scalability
- Stateless design allows horizontal scaling
- Thread-safe singleton ensures minimal memory overhead
- Async-ready architecture (can be adapted for async/await)

## Support

For technical support:
1. Check application logs for detailed error messages with request IDs
2. Verify Azure AD permissions and role assignments
3. Ensure all user emails exist in the organization
4. Test with simple requests first (single owner/member)
5. Consult Microsoft 365 service health dashboard for platform issues

---

**Service Version**: 2.0  
**Last Updated**: November 2025  
**Supported APIs**: Microsoft Graph API v1.0, Exchange Online REST API  
**Python Version**: 3.9+
