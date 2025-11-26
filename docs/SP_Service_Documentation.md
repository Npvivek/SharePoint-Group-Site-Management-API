# SharePoint Site Management API

A secure Flask-based REST API for automating Microsoft 365 Group and SharePoint Online site provisioning and management via Microsoft Graph API.

## Features

- **Provision SharePoint Sites**: Create Microsoft 365 Groups and associated SharePoint team sites
- **Retrieve Site Details**: Get consolidated information about a site, including group, owners, members, and site URL
- **Update Site Properties**: Change the display name, privacy, description, or users of a site
- **Delete Sites**: Permanently remove a Microsoft 365 Group and its associated SharePoint content
- **Secure App Authentication**: Uses Azure AD OAuth2 with app-only tokens via the MSAL Python library
- **Role-Synchronized User Management**: Owners and members are managed through Graph API synchronizations
- **Automatic Site Provisioning**: Handles asynchronous SharePoint site creation with polling mechanism

## Architecture Overview

### Component Design

The service follows a functional architecture pattern with helper functions for Graph API operations:

1. **Flask Application Layer**: Handles HTTP requests, routing, and error handling
2. **Authentication Layer** (`get_token()`): MSAL-based OAuth2 token acquisition for app-only authentication
3. **Graph API Helper Functions**:
   - `resolve_user_id()`: Converts user principal names (emails) to Azure AD Object IDs
   - `get_site_id()`: Retrieves SharePoint site ID from Group ID
   - `sync_group_users()`: Synchronizes owners or members to match desired state
4. **Route Handlers**: CRUD operations for SharePoint sites/M365 groups

### Key Design Decisions

#### 1. M365 Group = SharePoint Site
This service creates **Microsoft 365 Unified Groups** (not Distribution Lists), which automatically provision:
- SharePoint team site
- Outlook group mailbox
- Shared calendar
- OneDrive for Business document library
- Planner board (if licensed)

**Why this matters:** Microsoft 365 Groups provide integrated collaboration beyond email-only Distribution Lists.

#### 2. Asynchronous Site Provisioning with Polling
When a Group is created, SharePoint site provisioning happens asynchronously in the background (typically 30-60 seconds).

**Implementation:**
- Creates M365 Group immediately via Graph API
- Polls for site availability: 12 attempts × 5 seconds = 60 seconds maximum wait
- Returns site URL when ready or 504 timeout error

**Why polling is necessary:** SharePoint site provisioning is eventual consistency; immediate retrieval may return 404.

#### 3. Differential User Synchronization
The `sync_group_users()` function implements minimal-change synchronization:

**Algorithm:**
```
to_add = desired_users - current_users
to_remove = current_users - desired_users
```

**Benefits:**
- Reduces API calls (only changes are executed)
- Idempotent (safe to call repeatedly)
- Prevents unnecessary notifications to users

#### 4. Dual Update for Name Changes
When updating a group name, the service performs two operations:
1. Updates Microsoft 365 Group `displayName` via `/groups/{id}` endpoint
2. Updates SharePoint Site `displayName` via `/sites/{id}` endpoint

**Why both:** Group and site display names are separate properties; both should be synchronized for consistency.

#### 5. Soft Delete + Permanent Delete Pattern
The delete operation implements a two-phase process:
1. **Soft Delete**: Removes group (moves to Azure AD recycle bin)
2. **Permanent Delete**: Immediately purges from recycle bin with retry logic (up to 5 attempts)

**Why two phases:** Ensures complete deletion without 30-day retention period. Retry logic handles replication delays.

#### 6. Random Suffix in Mail Nickname
The `mailNickname` field uses: `slugify(name) + "-" + uuid.hex[:8]`

**Example:** "Project Team" → `project-team-a3f9b2c1`

**Why:** Ensures global uniqueness across the tenant, preventing conflicts with deleted or existing groups.

## Setup and Installation

### Prerequisites

- Python 3.9+
- Microsoft Azure App Registration with delegated and application Group/SharePoint permissions
- All required packages from `requirements.txt`

### Required API Permissions

In Azure Active Directory, your App Registration needs the following **Application** permissions (not Delegated):

#### Microsoft Graph API Permissions

| Permission | Purpose |
|------------|---------|
| `Group.ReadWrite.All` | Create, read, update, and delete Microsoft 365 Groups |
| `Directory.Read.All` | Read directory data including users and groups |
| `Sites.ReadWrite.All` | Read and write SharePoint site properties |
| `User.Read.All` | Resolve user emails to Object IDs for owner/member assignment |

#### Azure AD Directory Role Assignment

**Required:** The service principal (Azure AD app) must be assigned the **Group Administrator** role or higher.

**How to assign:**
1. Navigate to Azure AD → Roles and administrators
2. Search for "Group Administrator"
3. Click "Add assignments"
4. Select your application
5. Save

> **Note:** Without the Group Administrator role, group creation will fail with "Insufficient privileges" error.

### Installation Steps

1. **Clone and enter the repository**
2. **Setup virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install requirements:**
```bash
pip install flask flask-cors httpx msal pydantic python-slugify
```

4. **Configure environment variables:**

Create a `.env` file or set environment variables:
```env
TENANT_ID=your-azure-tenant-id
CLIENT_ID=your-azure-app-client-id
CLIENT_SECRET=your-azure-app-client-secret
```

**Configuration Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `TENANT_ID` | Yes | Azure AD Tenant ID |
| `CLIENT_ID` | Yes | Azure AD App Client ID |
| `CLIENT_SECRET` | Yes | Azure AD App Client Secret |

> **Security Note:** In production, load these from Azure Key Vault or secure environment variables, not hardcoded values.

## Running the Application

### For Development
```bash
python SP.py
```
Service available at: `http://localhost:7000`

### For Production
```bash
gunicorn -w 4 -b 0.0.0.0:7000 SP:app
```

## API Endpoints

### Base URL
`http://localhost:7000/api/sharepoint/site`

### 1. Create SharePoint Site

**Endpoint:** `POST /api/sharepoint/site`

**Description:** Creates a new Microsoft 365 group and provisions an associated SharePoint team site.

**Request JSON:**
```json
{
  "name": "Project Team Site",
  "ownerEmail": "manager@domain.com",
  "privacy": "Private",
  "description": "For the Project-X team.",
  "memberEmails": ["user1@domain.com", "user2@domain.com"]
}
```

**Request Schema:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Display name for the group and site |
| `ownerEmail` | string | ✅ | Email of the primary owner |
| `privacy` | string | ❌ | "Private" or "Public" (default: "Private") |
| `description` | string | ❌ | Description of the group/site |
| `memberEmails` | array[string] | ❌ | List of member emails |

**Implementation Details:**
- Group created with `groupTypes: ["Unified"]` to enable M365 features
- `mailEnabled: true` and `securityEnabled: false` for collaboration group
- Owner is resolved to Object ID and added via Graph API reference
- Site provisioning is polled for up to 60 seconds
- Members are synchronized after site is ready

**Success Response (201 Created):**
```json
{
  "groupId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "siteId": "contoso.sharepoint.com,a1b2c3d4-e5f6-7890-abcd-ef1234567890,b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "siteUrl": "https://contoso.sharepoint.com/sites/project-team-site-a3f9b2c1"
}
```

**Possible Errors:**
- `422 Unprocessable Entity`: Validation error (missing required fields)
- `404 Not Found`: Owner or member email doesn't exist in Azure AD
- `504 Gateway Timeout`: Site provisioning exceeded 60 seconds

### 2. Update Site or Group

**Endpoint:** `PATCH /api/sharepoint/site/{groupId}`

**Description:** Update name, description, privacy, owners, or members of an existing site.

**Request JSON (all fields optional):**
```json
{
  "name": "Updated Project Team Site",
  "description": "Updated description",
  "privacy": "Public",
  "ownerEmails": ["manager@domain.com", "newmanager@domain.com"],
  "memberEmails": ["user1@domain.com"]
}
```

**Implementation Details:**
- Group display name and privacy updated via `/groups/{id}` PATCH
- If name changes, SharePoint site title is also updated via `/sites/{id}` PATCH
- Owner and member lists are synchronized differentially (add missing, remove extra)
- Site title update failure is logged but doesn't fail the request

**Success Response (200 OK):**
```json
{
  "message": "Group a1b2c3d4-e5f6-7890-abcd-ef1234567890 updated successfully."
}
```

### 3. Get Site Details

**Endpoint:** `GET /api/sharepoint/site/{groupId}`

**Description:** Returns group name, members, owners, and SharePoint site URL.

**Implementation Details:**
- Queries group properties: `id`, `displayName`, `visibility`
- Fetches owners and members with `$select=userPrincipalName`
- Retrieves SharePoint site `webUrl` from `/groups/{id}/sites/root`

**Success Response (200 OK):**
```json
{
  "groupId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "Project Team Site",
  "privacy": "Private",
  "siteUrl": "https://contoso.sharepoint.com/sites/project-team-site-a3f9b2c1",
  "owners": ["manager@domain.com"],
  "members": ["user1@domain.com", "user2@domain.com"]
}
```

**Possible Errors:**
- `404 Not Found`: Resource not found (group may have been deleted)

### 4. Delete Site

**Endpoint:** `DELETE /api/sharepoint/site/{groupId}`

**Description:** Permanently deletes a Microsoft 365 Group and its associated SharePoint site.

**Implementation Details:**
1. Soft delete: `DELETE /groups/{id}` (moves to recycle bin)
2. Permanent delete: `DELETE /directory/deletedItems/{id}` with 5 retry attempts
3. 1-second delay between retry attempts for replication
4. Returns success if group not found (idempotent)

**Success Response (200 OK):**
```json
{
  "message": "Site deleted successfully."
}
```

**Important Notes:**
- Deletion is permanent and cannot be undone
- All associated content (SharePoint files, Teams conversations, Planner tasks) is deleted
- Deletion may take several minutes to fully propagate

## Important Implementation Notes

### Microsoft 365 Groups vs Distribution Lists

| Feature | M365 Groups (This API) | Distribution Lists |
|---------|----------------------|-------------------|
| Email functionality | ✅ Shared mailbox | ✅ Email forwarding only |
| SharePoint site | ✅ Auto-provisioned | ❌ None |
| Microsoft Teams | ✅ Can be Teams-enabled | ❌ None |
| Collaboration tools | ✅ Planner, Files, Calendar | ❌ None |
| Creation API | Graph API | Exchange PowerShell |
| Visibility | Private/Public | N/A |

### Site Provisioning Timing
- **Group creation**: Immediate (~1-2 seconds)
- **Site provisioning**: Asynchronous (30-60 seconds typical, up to 10 minutes in rare cases)
- **Service timeout**: 60 seconds (returns 504 if exceeded)

**Best Practice:** If 504 timeout occurs, the group was created successfully. Query the group after a few minutes to retrieve the site URL.

### Privacy Settings
- **Private**: Only members can access content
- **Public**: Anyone in the organization can discover and access

**Synchronization:** Privacy is synchronized between Group `visibility` and SharePoint site settings.

### User Assignment Requirements
- Only Azure AD users in the same tenant can be owners/members
- External users (guests) require different API endpoints (not supported in this service)
- Users must have appropriate Microsoft 365 licenses for full feature access

## Troubleshooting

### Common Issues

1. **"Insufficient privileges" error**
   - **Cause:** Missing Group Administrator role or API permissions
   - **Solution:**
     - Verify Group Administrator role assigned to app
     - Check all four Graph API permissions granted
     - Admin consent granted for permissions
     - Wait 5-10 minutes for role propagation

2. **"Site provisioning timed out" (504)**
   - **Cause:** SharePoint site taking longer than 60 seconds to provision
   - **Solution:**
     - Group was created successfully
     - Wait 2-5 minutes and query group via GET endpoint
     - Site URL will be available once provisioning completes
     - Check Microsoft 365 admin center for site status

3. **"User not found" error**
   - **Cause:** Email doesn't exist in Azure AD
   - **Solution:**
     - Verify email spelling
     - Check user exists in Azure AD
     - Ensure using UserPrincipalName (not alias)

4. **Site title didn't update with group name**
   - **Cause:** SharePoint site update failed (non-critical)
   - **Solution:**
     - Check logs for detailed error
     - Site title can be manually updated in SharePoint
     - Group display name still updated successfully

5. **Delete operation returns 404**
   - **Cause:** Group doesn't exist or already deleted
   - **Solution:**
     - This is expected behavior (idempotent)
     - Operation considered successful

## Security Considerations

### Authentication & Authorization
- App-only authentication using OAuth 2.0 client credentials flow
- No user context; operates with application-level permissions
- Tokens cached by MSAL library, auto-refreshed before expiration

### Data Privacy
- No PII logged except for troubleshooting purposes
- Client secrets never logged
- CORS enabled (configure for production environments)

### Network Security
- All communication over HTTPS
- Input validation via Pydantic models
- HTTP error responses include Graph API error details for debugging

### Client Secret Rotation

**Best Practice:**
- Rotate client secrets every 12-24 months
- Maintain two active secrets with staggered expiration dates
- Update `.env` file with new secret before old one expires
- Test authentication after rotation
- Monitor expiration dates in Azure portal

**Rotation Process:**
1. Generate new secret in Azure portal
2. Update `.env` with new `CLIENT_SECRET`
3. Restart application
4. Verify successful authentication
5. Delete old secret after confirmation

## Performance Considerations

### API Call Optimization
- Differential user synchronization minimizes Graph API calls
- Batch retrieval of user principal names (when applicable)
- MSAL token caching reduces authentication overhead

### Scalability
- Stateless design enables horizontal scaling
- No in-memory session state
- Thread-safe for concurrent requests

### Rate Limiting
Microsoft Graph API throttling limits:
- ~1200 requests per minute per app
- Service implements basic retry logic
- Consider implementing more sophisticated backoff for high-volume scenarios

## Support

For technical support:
1. Check application logs for Graph API error details
2. Verify Azure AD app registration and permissions
3. Ensure Group Administrator role assigned
4. Consult Microsoft 365 admin center for service health
5. Review Graph API documentation for specific error codes

**Useful Resources:**
- [Microsoft Graph API Documentation](https://docs.microsoft.com/en-us/graph/)
- [Microsoft 365 Groups Overview](https://docs.microsoft.com/en-us/microsoft-365/admin/create-groups/office-365-groups)
- [SharePoint Site Provisioning](https://docs.microsoft.com/en-us/sharepoint/dev/features/site-provisioning)

---

**Service Version**: 1.0  
**Last Updated**: November 2025  
**Supported API**: Microsoft Graph v1.0  
**Python Version**: 3.9+
