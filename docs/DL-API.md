# Distribution List Management API

A secure and robust Flask-based REST API for managing Microsoft 365 Distribution Lists. This service provides CRUD (Create, Read, Update, Delete) operations by interacting with the Microsoft Graph and Exchange Online APIs.

## Features

- **Create Distribution Lists**: Provision new DLs with specified owners and members
- **Retrieve DL Details**: Fetch comprehensive details for any existing DL, including members and owners
- **Update Distribution Lists**: Modify names, members, owners, and settings
- **Delete Distribution Lists**: Permanently remove a DL
- **Secure Authentication**: Uses the OAuth 2.0 client credentials flow to securely authenticate with Microsoft APIs
- **Data Validation**: Employs Pydantic for rigorous validation of all incoming request data
- **CORS Enabled**: Configurable Cross-Origin Resource Sharing for frontend integration

## Setup and Installation

### Prerequisites

- Python 3.9+
- `pip` and `venv`
- A Microsoft Azure App Registration with the necessary API permissions

### Required API Permissions

In Azure Active Directory, your App Registration needs the following **Application** permissions:

**Microsoft Graph:**
- `Directory.Read.All` - Validate user email addresses and organizational membership
- `User.Read.All` - Resolve user emails to Object IDs
- `Group.ReadWrite.All` - Update distribution list properties and membership
- `GroupMember.ReadWrite.All` - Add/remove members from distribution lists
- `Mail.Send` - Send notification emails (if needed)
- `Organization.ReadWrite.All` - Configure external sender permissions

**Office 365 Exchange Online:**
- `Exchange.ManageAsApp` - Manage Distribution Lists via Exchange Online REST API

**Directory Role Assignment:**
- `Exchange Administrator` or `Exchange Recipient Administrator` role must be assigned to the Azure AD application

### Installation Steps

1. **Clone the repository:**
```bash
git clone <repository-url>
cd distribution-list-api
```

2. **Create and activate a virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install flask flask-cors httpx msal pydantic python-slugify python-dotenv
```

4. **Configure Environment Variables:**
Create a `.env` file in the root directory:
```env
TENANT_ID=your-azure-tenant-id
CLIENT_ID=your-azure-app-client-id
CLIENT_SECRET=your-azure-app-client-secret
CUSTOM_DOMAIN=yourdomain.com
CORS_ORIGIN=*
```

## Running the Application

### For Development
Run the Flask application directly. The service will be available at `http://127.0.0.1:7000`.
```bash
python DL.py
```

### For Production
Use a production-grade WSGI server like Gunicorn:
```bash
gunicorn -w 4 -b 0.0.0.0:7000 DL:app
```

## API Documentation

### Base URL
```
http://localhost:7000/api
```

### Authentication
This API uses Azure AD application authentication. No additional headers are required from the client as authentication is handled internally.

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
| `404` | Not Found (DL doesn't exist) |
| `409` | Conflict (DL already exists) |
| `422` | Unprocessable Entity (Validation errors) |
| `500` | Internal Server Error |

## Endpoints

### 1. Create Distribution List

**Endpoint:** `POST /dl`

**Description:** Creates a new distribution list.

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

**Success Response (201 Created):**
```json
{
  "dlId": "marketing-team",
  "primaryEmail": "marketing-team@company.com"
}
```

**Possible Errors:**
- `409 Conflict`: A DL with that name already exists
- `404 Not Found`: One of the specified users (owner or member) does not exist
- `422 Unprocessable Entity`: Invalid request body (e.g., missing `name`, no owners)

### 2. Get Distribution List Details

**Endpoint:** `GET /dl/{dlId}`

**Description:** Retrieves full details for a specific distribution list. The `dlId` can be the name, alias, or primary email address.

**URL Parameter:**
- `dlId` (string): The identifier of the DL. Example: `marketing-team`

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

**Endpoint:** `PATCH /dl/{dlId}`

**Description:** Updates one or more properties of a distribution list. Send only the fields you want to change.

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

> **Note:** The `memberEmails` and `ownerEmails` fields are synchronized. The list you provide will become the definitive list, adding and removing users as necessary.

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

**Endpoint:** `DELETE /dl/{dlId}`

**Description:** Permanently deletes a distribution list.

**Success Response (200 OK):**
```json
{
  "message": "Distribution List '{dlId}' deleted successfully."
}
```

**Possible Errors:**
- `404 Not Found`: The specified distribution list does not exist

## Usage Examples

### Create a Distribution List
```bash
curl -X POST http://localhost:7000/api/dl \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Dev Team",
    "ownerEmails": ["manager@company.com"],
    "memberEmails": ["dev1@company.com", "dev2@company.com"],
    "allowExternalSenders": false
  }'
```

### Get Distribution List Details
```bash
curl -X GET http://localhost:7000/api/dl/dev-team
```

### Update Distribution List Members
```bash
curl -X PATCH http://localhost:7000/api/dl/dev-team \
  -H "Content-Type: application/json" \
  -d '{
    "memberEmails": ["dev1@company.com", "dev2@company.com", "dev3@company.com"]
  }'
```

### Delete Distribution List
```bash
curl -X DELETE http://localhost:7000/api/dl/dev-team
```

## Important Notes

### Distribution List vs Microsoft 365 Groups
This service creates **true Exchange Online Distribution Lists**, not Microsoft 365 Groups. Key differences:
- **Distribution Lists**: Appear as "Distribution List" type in Outlook, email-only functionality
- **Microsoft 365 Groups**: Appear as "Microsoft 365" type, include Teams, SharePoint, etc.

### Owner and Member Relationship
- **Owners**: Can manage the DL (add/remove members, change settings)
- **Members**: Receive emails sent to the DL
- **Important**: Owners are NOT automatically members - they must be explicitly added to receive emails

### Email Address Generation
- DL aliases are auto-generated using `slugify()` from the display name
- Primary email format: `{alias}@{CUSTOM_DOMAIN}`
- Example: "Marketing Team" → `marketing-team@company.com`

## Troubleshooting

### Common Issues

1. **"Role not supported" error**
   - Ensure Azure AD app has Exchange Administrator directory role assigned
   - Verify both API permissions and directory role are configured

2. **"User not found" error**
   - Check email address spelling
   - Verify user exists in Azure AD directory
   - Ensure user has proper license assignments

3. **"DL already exists" error**
   - Choose a different name for the distribution list
   - Check if a DL with similar alias already exists

4. **Connection timeout errors**
   - Verify network connectivity to Microsoft APIs
   - Check if firewall is blocking outbound connections

### Logging and Debugging

The service includes comprehensive logging with unique request IDs for tracing:
```
2025-08-24 19:00:00,123 - INFO - [abc123-def456] - Creating Distribution List: Marketing Team
```

Log levels:
- **INFO**: Normal operations, user validation, DL creation/updates
- **WARNING**: Non-critical failures (e.g., failed to add specific member)
- **ERROR**: API errors, authentication failures

## Security Considerations

- All API credentials are stored as environment variables
- Service uses OAuth 2.0 client credentials flow for secure authentication
- Input validation prevents injection attacks
- Request/response logging excludes sensitive data
- CORS is configurable for production environments

### Client Secret Rotation

- The client secret used for Azure AD app authentication should be rotated regularly, typically every 2 years or as mandated by your organization's security policies.
- Keep track of the expiry date of your client secret in the Azure portal.
- Update the `.env` configuration with the new client secret before the old one expires to ensure uninterrupted service.
- Regular rotation helps mitigate risks associated with leaked or compromised credentials.

## Support

For technical support:
1. Check application logs for detailed error messages with request IDs
2. Verify Azure AD permissions and role assignments
3. Ensure all user emails exist in the organization
4. Test with simple requests first (single owner/member)

---

**Service Version**: 2.0  
**Last Updated**: August 2025  
**Supported APIs**: Microsoft Graph API v1.0, Exchange Online REST API
