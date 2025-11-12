# SharePoint Site Management API

A secure Flask-based REST API for automating Microsoft 365 Group and SharePoint Online site provisioning and management via Microsoft Graph API.

## Features

- **Provision SharePoint Sites**: Create Microsoft 365 Groups and associated SharePoint team sites
- **Retrieve Site Details**: Get consolidated information about a site, including group, owners, members, and site URL
- **Update Site Properties**: Change the display name, privacy, description, or users of a site
- **Delete Sites**: Permanently remove a Microsoft 365 Group and its associated SharePoint content
- **Secure App Authentication**: Uses Azure AD OAuth2 with app-only tokens via the MSAL Python library
- **Role-Synchronized User Management**: Owners and members are managed through Graph API synchronizations

## Setup and Installation

### Prerequisites

- Python 3.9+
- Microsoft Azure App Registration with delegated and application Group/SharePoint permissions
- All required packages from `requirements.txt`

### API Permissions

- Microsoft Graph API (Application permissions):
  - `Group.ReadWrite.All`
  - `Directory.Read.All`
  - `Sites.ReadWrite.All`
  - `User.Read.All`
- Azure Role Assignment:
  - The app must be assigned as a Group Administrator or higher

### Installation Steps

1. **Clone and enter the repository**
2. **Setup virtual environment**
3. **Install requirements** (using pip and requirements.txt)
4. **Configure environment variables**: TENANT_ID, CLIENT_ID, CLIENT_SECRET, etc., in your environment or `.env` file.

## API Endpoints

### Base URL
`http://localhost:7000/api/sharepointsite`

### 1. Create SharePoint Site
- `POST /api/sharepointsite`
- Creates a new Microsoft 365 group and SharePoint site

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
**Response:** Group and site info (IDs, site url).

### 2. Update Site or Group
- `PATCH /api/sharepointsite/{groupId}`
- Update name, description, privacy, owners, or members of an existing site

### 3. Get Site Details
- `GET /api/sharepointsite/{groupId}`
- Returns group name, members, owners, and SharePoint site URL

### 4. Delete Site
- `DELETE /api/sharepointsite/{groupId}`
- Deletes a group and associated SharePoint resources (permanent)

## Error Handling

- Consistent JSON error structure, logs detailed errors (with HTTP code)
- Translates Graph API/network errors into actionable responses

## Examples

#### Create Site
```bash
curl -X POST http://localhost:7000/api/sharepointsite \
 -H "Content-Type: application/json" \
 -d '{"name": "HR Site", "ownerEmail": "hr@domain.com", "privacy": "Private", "description": "HR Department.", "memberEmails": ["member1@domain.com"]}'
```

#### Update Site
```bash
curl -X PATCH http://localhost:7000/api/sharepointsite/<groupId> \
 -H "Content-Type: application/json" \
 -d '{"name": "Updated HR Site", "memberEmails": ["user2@domain.com"]}'
```

#### Get Details
```bash
curl -X GET http://localhost:7000/api/sharepointsite/<groupId>
```

#### Delete Site
```bash
curl -X DELETE http://localhost:7000/api/sharepointsite/<groupId>
```

## Notes
- Only Azure AD users present in the tenant can be assigned as owners or members.
- Site display name and privacy are synchronized between group and site.
- MS Graph API credentials must be rotated periodically (client secrets typically expire every 1–2 years).

## Security & Maintenance
- Never expose client secrets or tokens.
- All API actions require App-Only authentication configured in Azure.
- Token and error logging is file-backed for auditing.

### Client Secret Rotation
- Client secrets should be rotated every 1–2 years as per organizational security policies
- Update `.env` with new credentials before old ones expire
- Monitor expiration dates in Azure portal

## Support
- For Graph auth or permissions errors, check Azure app registration, roles, and scope grants.
- Use logs (`SP.log` or console) for debugging.

---
**Service Version**: 1.0  
**Last Updated**: Nov 2025  
**Supported API**: Microsoft Graph v1.0
