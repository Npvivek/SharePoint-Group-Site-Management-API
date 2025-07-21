# SharePoint Site Management API

This document provides a complete reference for using the API to manage Microsoft 365 Groups and their associated SharePoint sites.

---

## General Information

### Base URL

All API endpoints are relative to the following base URL:

`http://localhost:7000`

### Authentication

The service handles authentication with the Microsoft Graph API automatically using backend credentials. No `Authorization` headers are required from the client.

### Common Error Response

When an API call to Microsoft Graph fails, the service will forward the error in a structured format. A `500 Internal Server Error` will be returned for unexpected server-side issues.

**Example Graph API Error (`4xx` or `5xx` status code):**
```json
{
    "error": "Microsoft Graph API Error",
    "details": {
        "error": {
            "code": "Request_ResourceNotFound",
            "message": "Resource '...' does not exist or one of its queried reference-property objects are not present.",
            "innerError": {}
        }
    }
}
```

---

## API Endpoints Reference

### 1. Get Site Details

Retrieves consolidated details for a specific group and its SharePoint site, including a full list of its owners and members. This is useful for verifying the current state of a site.

-   **Method:** `GET`
-   **Endpoint:** `/api/sharepoint/site/{groupId}`
-   **Example URL:** `http://localhost:7000/api/sharepoint/site/a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d`

#### Request

##### Path Parameters

| Parameter | Type   | Description                      |
| :-------- | :----- | :------------------------------- |
| `groupId` | string | **Required.** The ID of the group. |

#### Response

##### `200 OK`

Returns a JSON object with the site's details.

```json
{
  "groupId": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
  "name": "Project Apollo",
  "privacy": "Private",
  "siteUrl": "https://corp.sharepoint.com/sites/ProjectApollo-a1b2",
  "owners": [
    "project.lead@corp.com"
  ],
  "members": [
    "dev1@corp.com",
    "analyst@corp.com"
  ]
}
```

##### `404 Not Found`

Returned if the `groupId` does not exist or has already been deleted.

---

### 2. Create a SharePoint Site

Creates a new Microsoft 365 Group and its associated SharePoint site. The site provisioning can take up to a minute; the API will wait for this process to complete before responding.

-   **Method:** `POST`
-   **Endpoint:** `/api/sharepoint/site`
-   **Example URL:** `http://localhost:7000/api/sharepoint/site`

#### Request

##### Body Parameters

| Parameter      | Type           | Description                                                                                             |
| :------------- | :------------- | :------------------------------------------------------------------------------------------------------ |
| `name`         | string         | **Required.** The display name for the new site and group.                                              |
| `ownerEmail`   | string         | **Required.** The email address (User Principal Name) of the primary owner.                               |
| `privacy`      | string         | *Optional.* The privacy setting. Can be `"Private"` or `"Public"`. Defaults to `"Private"`.              |
| `description`  | string         | *Optional.* A description for the site.                                                                 |
| `memberEmails` | array[string]  | *Optional.* A list of member email addresses to add to the group.                                       |

##### Example Body

```json
{
  "name": "Project Apollo",
  "ownerEmail": "project.lead@corp.com",
  "privacy": "Private",
  "description": "Workspace for the Project Apollo marketing campaign.",
  "memberEmails": ["dev1@corp.com"]
}
```

#### Response

##### `201 Created`

Returns a JSON object with the new site's identifiers.

```json
{
  "groupId": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
  "siteId": "corp.sharepoint.com,d4e5f6a1,...",
  "siteUrl": "https://corp.sharepoint.com/sites/ProjectApollo-a1b2"
}
```

---

### 3. Update Site Details

Updates an existing site's properties.

-   **Method:** `PATCH`
-   **Endpoint:** `/api/sharepoint/site/{groupId}`
-   **Example URL:** `http://localhost:7000/api/sharepoint/site/a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d`

#### Request

##### Path Parameters

| Parameter | Type   | Description                      |
| :-------- | :----- | :------------------------------- |
| `groupId` | string | **Required.** The ID of the group to update. |

##### Body Parameters
All body parameters are optional. Include only the fields you wish to change.

| Parameter      | Type           | Description                                                                                             |
| :------------- | :------------- | :------------------------------------------------------------------------------------------------------ |
| `name`         | string         | *Optional.* The new display name for the site.                                                          |
| `description`  | string         | *Optional.* The new description. Sending an empty string (`""`) will clear the description.             |
| `privacy`      | string         | *Optional.* The new privacy setting (`"Private"` or `"Public"`).                                        |
| `ownerEmails`  | array[string]  | *Optional.* The **complete and final list** of owner emails. See notes below.                           |
| `memberEmails` | array[string]  | *Optional.* The **complete and final list** of member emails. See notes below.                          |

##### Important Notes on User Synchronization
When you provide `ownerEmails` or `memberEmails`, the API performs a **full synchronization**. This means:
-   **Users will be added:** Any email in your list that is not already a member/owner will be added.
-   **Users will be removed:** Any current member/owner whose email is *not* in your list will be removed.
-   To simply add users without removing others, you must first `GET` the current list, append the new users, and then `PATCH` with the combined list.

##### Example Body 1: Update Description and Sync Members
```json
{
  "description": "Final workspace for the campaign.",
  "memberEmails": ["dev1@corp.com", "analyst@corp.com"]
}
```

##### Example Body 2: Update Only the Site Name
```json
{
  "name": "Project Apollo (Archived)"
}
```

#### Response

##### `200 OK`

Returns a success message.

```json
{
  "message": "Group a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d updated successfully."
}
```

---

### 4. Delete a SharePoint Site

Permanently deletes a Microsoft 365 Group and its associated SharePoint site.

-   **Method:** `DELETE`
-   **Endpoint:** `/api/sharepoint/site/{groupId}`
-   **Example URL:** `http://localhost:7000/api/sharepoint/site/a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d`

#### Request

##### Path Parameters

| Parameter | Type   | Description                      |
| :-------- | :----- | :------------------------------- |
| `groupId` | string | **Required.** The ID of the group to delete. |

##### Body
No request body is required.

#### Response

##### `204 No Content`
A successful deletion returns an empty response with a `204 No Content` status code.

##### Important Notes
-   **This action is irreversible and cannot be undone.**
-   The API performs a two-step deletion process to ensure the site is permanently removed, not just soft-deleted.